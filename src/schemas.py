from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class MoleculeCreate(BaseModel):
    """Create a new molecule."""
    smiles: str = Field(..., min_length=1, max_length=4096, description="SMILES notation", examples=["CCO"])


class MoleculeUpdate(BaseModel):
    """Update a molecule."""
    smiles: Optional[str] = Field(None, min_length=1, max_length=4096, description="New SMILES notation")


class MoleculeOut(BaseModel):
    """Molecule response."""
    id: UUID = Field(..., description="Unique identifier")
    smiles: str = Field(..., description="SMILES notation")


class TaskRequest(BaseModel):
    """Async task request."""
    substructure: str = Field(..., description="SMILES/SMARTS pattern to search")
    limit: Optional[int] = Field(None, ge=1, le=10_000, description="Maximum number of results to return")


class TaskStatus(BaseModel):
    """Task status response."""
    task_id: str = Field(..., description="Task identifier")
    status: str = Field(..., description="Status: PENDING, SUCCESS, FAILURE")
    result: Optional[list[str]] = Field(None, description="Results when status is SUCCESS")


class SubstructureQueryParams(BaseModel):
    """Substructure search parameters."""
    substructure: str = Field(..., description="SMILES/SMARTS pattern")
    limit: Optional[int] = Field(None, ge=1, le=10_000, description="Maximum number of results to return")


class SubstructureSearchResponse(BaseModel):
    """Substructure search results."""
    substructure: str
    limit: Optional[int]
    count: int = Field(..., description="Number of matches found")
    hits: list[str] = Field(..., description="Matching SMILES")
    cached: bool = Field(False, description="Result from cache")
