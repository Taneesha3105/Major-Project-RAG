from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Message(BaseModel):
    message: str


class Citation(BaseModel):
    """A pointer back to the exact evidence a statement is grounded in."""

    index: int
    chunk_id: int
    document_id: str
    filename: str
    category: str
    page_number: int | None = None
    section: str | None = None
    snippet: str
    score: float | None = None
