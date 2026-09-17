from pydantic import BaseModel


class EmbeddingGenerationResponse(BaseModel):
    document_id: int
    filename: str
    total_chunks: int
    embedded_chunks: int
    skipped_chunks: int
    message: str
