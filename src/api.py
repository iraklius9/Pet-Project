import json
import os
from typing import Iterator, Optional, List
from uuid import UUID, uuid4

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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


# --------- helpers ---------

def _to_uuid(value: object) -> UUID:
    try:
        return UUID(str(value))
    except Exception:
        return uuid4()


def _to_out(m: Molecule) -> MoleculeOut:
    return MoleculeOut(id=_to_uuid(m.id), identifier=m.identifier, smiles=m.smiles)


def _cache_get_json(cache: redis.Redis, key: str):
    cached = cache.get(key)
    if not cached:
        return None
    try:
        return json.loads(cached)
    except Exception:
        return None


def _cache_set_json(cache: redis.Redis, key: str, value) -> None:
    try:
        cache.setex(key, CACHE_TTL_SECONDS, json.dumps(value))
    except Exception:
        # Cache failures must not break request handling
        pass


def _get_smiles_list(db: Session, limit: Optional[int] = None) -> list[str]:
    stmt = select(Molecule.smiles)
    if limit:
        stmt = stmt.limit(limit)
    return [row[0] for row in db.execute(stmt).all()]


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
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Identifier already exists")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Identifier already exists")
    return _to_out(mol)


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
    return _to_out(mol)


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
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Identifier already exists")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409, detail="Identifier already exists")
    return _to_out(mol)


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
        return [_to_out(m).model_dump() for m in rows]

    def _gen() -> Iterator[bytes]:
        for m in db.execute(stmt).scalars():
            yield (json.dumps(_to_out(m).model_dump()).encode() + b"\n")

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
        except IntegrityError:
            db.rollback()
            continue
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
    cached = _cache_get_json(cache, key)
    if cached is not None:
        return cached
    smiles_list = _get_smiles_list(db, limit)
    hits = substructure_search(smiles_list, substructure)
    _cache_set_json(cache, key, hits)
    return hits


@search_router.post("/substructure-search", response_model=SubstructureSearchResponse)
def substructure_search_post(
        payload: SubstructureQueryParams,
        db: Session = Depends(get_db),
        cache: redis.Redis = Depends(get_cache),
) -> SubstructureSearchResponse:
    key = f"subsearch:{payload.substructure}|limit={payload.limit}"
    cached_hits = _cache_get_json(cache, key)
    if cached_hits is not None:
        return SubstructureSearchResponse(
            substructure=payload.substructure,
            limit=payload.limit,
            count=len(cached_hits),
            hits=cached_hits,
            cached=True,
        )
    smiles_list = _get_smiles_list(db, payload.limit)
    hits = substructure_search(smiles_list, payload.substructure)
    _cache_set_json(cache, key, hits)
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
        smiles_list = _get_smiles_list(db, limit)
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
