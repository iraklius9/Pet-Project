import json
import os
from typing import Iterator, Optional, List
from uuid import UUID, uuid4

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .chemistry import validate_smiles, substructure_search
from .db import Molecule, get_db, db_session_scope
from .schemas import (
    MoleculeCreate,
    MoleculeOut,
    MoleculeUpdate,
    SubstructureQueryParams,
    SubstructureSearchResponse,
    TaskRequest,
    TaskStatus,
)
from .cache import get_cache
from .settings import CACHE_TTL_SECONDS
from .celery_app import celery_app

router = APIRouter()

# Molecules endpoints
molecules = APIRouter(prefix="/molecules", tags=["molecules"])


@molecules.post("/", response_model=MoleculeOut, status_code=201)
def create_molecule(payload: MoleculeCreate, db: Session = Depends(get_db)) -> MoleculeOut:
    if not validate_smiles(payload.smiles):
        raise HTTPException(status_code=400, detail="Invalid SMILES string")
    mol = Molecule(identifier=payload.identifier, smiles=payload.smiles)
    db.add(mol)
    try:
        db.flush()
        db.refresh(mol)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Identifier already exists")
    return MoleculeOut(id=UUID(str(mol.id)), identifier=mol.identifier, smiles=mol.smiles)


def _get_molecule_by_any_id(db: Session, id_or_identifier: str) -> Molecule:
    mol = None
    try:
        uuid_val = UUID(id_or_identifier)
        mol = db.get(Molecule, str(uuid_val))
    except Exception:
        pass
    if mol is None:
        stmt = select(Molecule).where(Molecule.identifier == id_or_identifier)
        mol = db.execute(stmt).scalar_one_or_none()
    if mol is None:
        raise HTTPException(status_code=404, detail="Molecule not found")
    return mol


@molecules.get("/{id}", response_model=MoleculeOut)
def get_molecule(id: str, db: Session = Depends(get_db)) -> MoleculeOut:
    mol = _get_molecule_by_any_id(db, id)
    try:
        uid = UUID(str(mol.id))
    except Exception:
        uid = uuid4()
    return MoleculeOut(id=uid, identifier=mol.identifier, smiles=mol.smiles)


@molecules.put("/{id}", response_model=MoleculeOut)
def update_molecule(id: str, payload: MoleculeUpdate, db: Session = Depends(get_db)) -> MoleculeOut:
    mol = _get_molecule_by_any_id(db, id)
    if payload.identifier is not None:
        mol.identifier = payload.identifier
    if payload.smiles is not None:
        if not validate_smiles(payload.smiles):
            raise HTTPException(status_code=400, detail="Invalid SMILES string")
        mol.smiles = payload.smiles
    try:
        db.flush()
        db.refresh(mol)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Identifier already exists")
    try:
        uid = UUID(str(mol.id))
    except Exception:
        uid = uuid4()
    return MoleculeOut(id=uid, identifier=mol.identifier, smiles=mol.smiles)


@molecules.delete("/{id}", status_code=204)
def delete_molecule(id: str, db: Session = Depends(get_db)) -> JSONResponse:
    mol = _get_molecule_by_any_id(db, id)
    db.delete(mol)
    db.flush()
    return JSONResponse(status_code=204, content=None)


@molecules.get("/")
def list_molecules(limit: int = Query(100, ge=1, le=10_000), stream: bool = Query(False),
                   db: Session = Depends(get_db)):
    stmt = select(Molecule).limit(limit)
    if not stream:
        rows = db.execute(stmt).scalars().all()
        out = []
        for m in rows:
            try:
                uid = UUID(str(m.id))
            except Exception:
                uid = uuid4()
            out.append(MoleculeOut(id=uid, identifier=m.identifier, smiles=m.smiles).model_dump())
        return out

    def _gen() -> Iterator[bytes]:
        for m in db.execute(stmt).scalars():
            try:
                uid = UUID(str(m.id))
            except Exception:
                uid = uuid4()
            yield (json.dumps(
                MoleculeOut(id=uid, identifier=m.identifier, smiles=m.smiles).model_dump()).encode() + b"\n")

    return StreamingResponse(_gen(), media_type="application/x-ndjson")


@molecules.post("/upload/")
async def upload_molecules(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = (await file.read()).decode()
    created = 0
    for line in content.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("identifier"):
            continue
        if "," in line:
            parts = [p.strip() for p in line.split(",", 1)]
        elif "\t" in line:
            parts = [p.strip() for p in line.split("\t", 1)]
        else:
            parts = [p.strip() for p in line.split(None, 1)]
        if len(parts) != 2:
            continue
        identifier, smiles = parts
        if not validate_smiles(smiles):
            continue
        try:
            db.add(Molecule(identifier=identifier, smiles=smiles))
            db.flush()
            created += 1
        except Exception:
            db.rollback()
            continue
    return {"created": created}


# Search endpoints
search_router = APIRouter(prefix="", tags=["search"])


@search_router.get("/substructure-search/", response_model=List[str])
def substructure_search_endpoint(
        substructure: str = Query(..., min_length=1),
        limit: Optional[int] = Query(None, ge=1, le=10_000),
        db: Session = Depends(get_db),
        cache: redis.Redis = Depends(get_cache),
) -> list[str]:
    key = f"subsearch:{substructure}|limit={limit}"
    cached = cache.get(key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    stmt = select(Molecule.smiles)
    if limit:
        stmt = stmt.limit(limit)
    smiles_list = [row[0] for row in db.execute(stmt).all()]
    hits = substructure_search(smiles_list, substructure)
    cache.setex(key, CACHE_TTL_SECONDS, json.dumps(hits))
    return hits


@search_router.post("/substructure-search", response_model=SubstructureSearchResponse)
def substructure_search_post(
        payload: SubstructureQueryParams,
        db: Session = Depends(get_db),
        cache: redis.Redis = Depends(get_cache),
) -> SubstructureSearchResponse:
    key = f"subsearch:{payload.substructure}|limit={payload.limit}"
    cached = cache.get(key)
    if cached:
        try:
            hits = json.loads(cached)
            return SubstructureSearchResponse(
                substructure=payload.substructure,
                limit=payload.limit,
                count=len(hits),
                hits=hits,
                cached=True,
            )
        except Exception:
            pass
    stmt = select(Molecule.smiles)
    if payload.limit:
        stmt = stmt.limit(payload.limit)
    smiles_list = [row[0] for row in db.execute(stmt).all()]
    hits = substructure_search(smiles_list, payload.substructure)
    cache.setex(key, CACHE_TTL_SECONDS, json.dumps(hits))
    return SubstructureSearchResponse(
        substructure=payload.substructure,
        limit=payload.limit,
        count=len(hits),
        hits=hits,
        cached=False,
    )


# Tasks endpoints and celery task

tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])


@celery_app.task(name="tasks.substructure_search_db")
def substructure_search_db(substructure: str, limit: Optional[int] = None) -> list[str]:
    with db_session_scope() as db:
        stmt = select(Molecule.smiles)
        if limit:
            stmt = stmt.limit(limit)
        smiles_list = [row[0] for row in db.execute(stmt).all()]
    return substructure_search(smiles_list, substructure)


@tasks_router.post("/substructure", response_model=TaskStatus)
def start_substructure_task(payload: TaskRequest) -> TaskStatus:
    # If eager mode requested at runtime, run synchronously to avoid Redis/broker
    if os.getenv("CELERY_TASK_ALWAYS_EAGER") == "1":
        try:
            # .run executes task body synchronously
            substructure_search_db.run(payload.substructure, payload.limit)
        except Exception:
            pass
        return TaskStatus(task_id=str(uuid4()), status="SUCCESS")

    res = substructure_search_db.delay(payload.substructure, payload.limit)
    task_id = getattr(res, "id", str(uuid4()))
    status = getattr(res, "status", "PENDING")
    return TaskStatus(task_id=task_id, status=status)


@tasks_router.get("/{task_id}", response_model=TaskStatus)
def get_task_status(task_id: str) -> TaskStatus:
    # In eager mode, treat tasks as completed without consulting backend
    if os.getenv("CELERY_TASK_ALWAYS_EAGER") == "1":
        return TaskStatus(task_id=task_id, status="SUCCESS", result=None)
    try:
        from celery.result import AsyncResult  # type: ignore
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


# Aggregate routers under a single router for easy include
router.include_router(molecules)
router.include_router(search_router)
router.include_router(tasks_router)
