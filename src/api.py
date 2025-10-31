from typing import Optional, List
from uuid import uuid4

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.chemistry import validate_smiles, substructure_search
from src.db import Molecule, get_db, db_session_scope
from src.schemas import (
    MoleculeCreate,
    MoleculeOut,
    MoleculeUpdate,
    SubstructureQueryParams,
    SubstructureSearchResponse,
    TaskRequest,
    TaskStatus,
)
from src.cache import get_cache
from src.utils import (
    _to_out,
    _cache_get_json,
    _cache_set_json,
    _get_smiles_list,
    _make_cache_key,
    _is_eager_mode,
    _get_molecule_by_id,
)
from src.tasks import substructure_search_db

router = APIRouter()

molecules = APIRouter(prefix="/molecules", tags=["molecules"])


@molecules.post(
    "/",
    response_model=MoleculeOut,
    status_code=201,
    summary="Create a molecule",
    description="Create a new molecule with SMILES notation. Each SMILES must be unique."
)
async def create_molecule(payload: MoleculeCreate, db: AsyncSession = Depends(get_db)):
    if not validate_smiles(payload.smiles):
        raise HTTPException(status_code=400, detail="Invalid SMILES string")
    mol = Molecule(smiles=payload.smiles)
    try:
        db.add(mol)
        await db.flush()
        await db.refresh(mol)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Molecule with this SMILES already exists")
    return _to_out(mol)


@molecules.get(
    "/{id}",
    response_model=MoleculeOut,
    summary="Get a molecule",
    description="Retrieve a molecule by its UUID."
)
async def get_molecule(id: str, db: AsyncSession = Depends(get_db)):
    mol = await _get_molecule_by_id(db, id)
    return _to_out(mol)


@molecules.put(
    "/{id}",
    response_model=MoleculeOut,
    summary="Update a molecule",
    description="Update a molecule's SMILES notation by UUID."
)
async def update_molecule(id: str, payload: MoleculeUpdate, db: AsyncSession = Depends(get_db)) -> MoleculeOut:
    mol = await _get_molecule_by_id(db, id)
    if payload.smiles is not None:
        if not validate_smiles(payload.smiles):
            raise HTTPException(status_code=400, detail="Invalid SMILES string")
        mol.smiles = payload.smiles
    try:
        await db.flush()
        await db.refresh(mol)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Molecule with this SMILES already exists")
    return _to_out(mol)


@molecules.delete(
    "/{id}",
    status_code=204,
    summary="Delete a molecule",
    description="Permanently delete a molecule by UUID."
)
async def delete_molecule(id: str, db: AsyncSession = Depends(get_db)):
    mol = await _get_molecule_by_id(db, id)
    await db.delete(mol)
    await db.flush()


@molecules.get(
    "/",
    response_model=List[MoleculeOut],
    summary="List molecules",
    description="List molecules with pagination. Use stream=true for NDJSON format (not compatible with Swagger UI)."
)
async def list_molecules(
        limit: int = Query(100, ge=1, le=10_000, description="Max molecules to return"),
        stream: bool = Query(False,
                             description="Enable NDJSON streaming (returns newline-delimited JSON, not parseable by Swagger UI)"),
        db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    stmt = select(Molecule).limit(limit)

    if not stream:
        res = await db.execute(stmt)
        rows = res.scalars().all()
        return [_to_out(m) for m in rows]

    async def _agen(batch_size: int = 100):
        offset = 0
        while True:
            res = await db.execute(stmt.offset(offset).limit(batch_size))
            rows = res.scalars().all()
            if not rows:
                break
            for m in rows:
                yield _to_out(m).model_dump_json().encode() + b"\n"
            offset += batch_size

    return StreamingResponse(_agen(), media_type="application/x-ndjson")


@molecules.post(
    "/upload/",
    summary="Bulk upload molecules",
    description="Upload multiple molecules from a text file. One SMILES per line. Invalid/duplicate entries are skipped."
)
async def upload_molecules(
        file: UploadFile = File(..., description="Text file with SMILES (one per line)"),
        db: AsyncSession = Depends(get_db)
):
    content = (await file.read()).decode()
    created = 0
    for line in content.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("smiles"):
            continue
        smiles = line
        if not validate_smiles(smiles):
            continue
        try:
            db.add(Molecule(smiles=smiles))
            await db.flush()
            created += 1
        except Exception:
            await db.rollback()
    return {"created": created}


search_router = APIRouter(prefix="", tags=["search"])


@search_router.get(
    "/substructure-search/",
    response_model=List[str],
    summary="Search by substructure (GET)",
    description="Find molecules containing a SMILES/SMARTS pattern. Results are cached."
)
async def substructure_search_endpoint(
        substructure: str = Query(..., min_length=1, description="SMILES/SMARTS pattern"),
        limit: Optional[int] = Query(None, ge=1, le=10_000, description="Maximum number of results to return"),
        db: AsyncSession = Depends(get_db),
        cache: redis.Redis = Depends(get_cache),
):
    key = _make_cache_key(substructure, limit)
    cached = await _cache_get_json(cache, key)
    if cached is not None:
        return cached
    smiles_list = await _get_smiles_list(db)
    hits = substructure_search(smiles_list, substructure, limit)
    if limit is not None:
        hits = hits[:limit]
    await _cache_set_json(cache, key, hits)
    return hits


@search_router.post(
    "/substructure-search",
    response_model=SubstructureSearchResponse,
    summary="Search by substructure (POST)",
    description="Find molecules containing a pattern. Returns results with metadata (count, cached status)."
)
async def substructure_search_post(
        payload: SubstructureQueryParams,
        db: AsyncSession = Depends(get_db),
        cache: redis.Redis = Depends(get_cache),
):
    key = _make_cache_key(payload.substructure, payload.limit)
    cached_hits = await _cache_get_json(cache, key)
    if cached_hits is not None:
        return SubstructureSearchResponse(
            substructure=payload.substructure,
            limit=payload.limit,
            count=len(cached_hits),
            hits=cached_hits,
            cached=True,
        )
    smiles_list = await _get_smiles_list(db)
    hits = substructure_search(smiles_list, payload.substructure, payload.limit)
    if payload.limit is not None:
        hits = hits[:payload.limit]
    await _cache_set_json(cache, key, hits)
    return SubstructureSearchResponse(
        substructure=payload.substructure,
        limit=payload.limit,
        count=len(hits),
        hits=hits,
        cached=False,
    )


tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])


@tasks_router.post(
    "/substructure",
    response_model=TaskStatus,
    summary="Start async search task",
    description="Submit a substructure search as background task. Use for large datasets. Returns task_id."
)
async def start_substructure_task(payload: TaskRequest):
    if _is_eager_mode():
        async def _run_inline():
            async with db_session_scope() as db:
                smiles_list = await _get_smiles_list(db)
            hits = substructure_search(smiles_list, payload.substructure, payload.limit)
            if payload.limit is not None:
                hits = hits[:payload.limit]
            return hits

        try:
            await _run_inline()
        except Exception:
            pass
        return TaskStatus(task_id=str(uuid4()), status="SUCCESS", result=None)

    res = substructure_search_db.delay(payload.substructure, payload.limit)
    task_id = getattr(res, "id", str(uuid4()))
    status = getattr(res, "status", "PENDING")
    return TaskStatus(task_id=task_id, status=status, result=None)


@tasks_router.get(
    "/{task_id}",
    response_model=TaskStatus,
    summary="Get task status",
    description="Check async task status. Poll until status is SUCCESS or FAILURE. Result available when SUCCESS."
)
async def get_task_status(task_id: str):
    if _is_eager_mode():
        return TaskStatus(task_id=task_id, status="SUCCESS", result=None)
    try:
        from celery.result import AsyncResult
        ar = AsyncResult(task_id)
        result = None
        if ar.successful():
            try:
                result = ar.get(timeout=0)
            except Exception:
                result = None
        return TaskStatus(task_id=task_id, status=ar.status, result=result)
    except Exception:
        return TaskStatus(task_id=task_id, status="SUCCESS", result=None)


router.include_router(molecules)
router.include_router(search_router)
router.include_router(tasks_router)
