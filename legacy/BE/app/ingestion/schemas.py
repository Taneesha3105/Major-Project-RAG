from pydantic import BaseModel, Field, field_validator


class TextIngestRequest(BaseModel):
    text: str = Field(..., min_length=1)
    filename: str | None = Field(default=None, max_length=255)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Text content cannot be empty.")
        return cleaned


class DocumentIngestResponse(BaseModel):
    document_id: int
    filename: str
    content_hash: str
    chunk_count: int
    duplicate: bool
    source_type: str
    source_format: str | None = None
    parser_name: str | None = None
    message: str
