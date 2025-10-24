from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class MoleculeCreate(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=255)
    smiles: str = Field(..., min_length=1, max_length=4096)


class MoleculeUpdate(BaseModel):
    identifier: Optional[str] = Field(None, min_length=1, max_length=255)
    smiles: Optional[str] = Field(None, min_length=1, max_length=4096)


class MoleculeOut(BaseModel):
    id: UUID
    identifier: str
    smiles: str


class TaskRequest(BaseModel):
    substructure: str
    limit: Optional[int] = Field(None, ge=1, le=10_000)


class TaskStatus(BaseModel):
    task_id: str
    status: str
    result: Optional[list[str]] = None


class SubstructureQueryParams(BaseModel):
    substructure: str
    limit: Optional[int] = Field(None, ge=1, le=10_000)


class SubstructureSearchResponse(BaseModel):
    substructure: str
    limit: Optional[int]
    count: int
    hits: list[str]
    cached: bool = False
