import json
import os
from typing import Optional
from uuid import UUID

import redis.asyncio as redis
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import Molecule
from src.schemas import MoleculeOut
from src.settings import CACHE_TTL_SECONDS


def _to_out(m: Molecule):
    return MoleculeOut(id=m.id, smiles=m.smiles)


async def _cache_get_json(cache: redis.Redis, key: str):
    cached = await cache.get(key)
    if not cached:
        return None
    try:
        return json.loads(cached)
    except Exception:
        return None


async def _cache_set_json(cache: redis.Redis, key: str, value):
    try:
        await cache.setex(key, CACHE_TTL_SECONDS, json.dumps(value))
    except Exception:
        pass


async def _get_smiles_list(db: AsyncSession):
    stmt = select(Molecule.smiles)
    res = await db.execute(stmt)
    return res.scalars().all()


def _make_cache_key(substructure: str, limit: Optional[int]):
    return f"subsearch:{substructure}|limit={limit}"


def _is_eager_mode() -> bool:
    return os.getenv("CELERY_TASK_ALWAYS_EAGER") == "1"


async def _get_molecule_by_id(db: AsyncSession, id: str):
    try:
        uuid_val = UUID(id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Molecule not found")

    mol = await db.get(Molecule, uuid_val)
    if mol is None:
        raise HTTPException(status_code=404, detail="Molecule not found")
    return mol
