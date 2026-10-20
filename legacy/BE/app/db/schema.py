import logging
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)

POSTGRES_EXTENSION_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
)

HNSW_CHUNK_EMBEDDING_INDEX_NAME = "ix_chunks_embedding_hnsw"
SEARCH_VECTOR_GIN_INDEX_NAME = "ix_chunks_search_vector_gin"
POSTGRES_TEXT_SEARCH_CONFIG = "english"
SEARCH_VECTOR_GENERATED_EXPRESSION = (
    f"to_tsvector('{POSTGRES_TEXT_SEARCH_CONFIG}', lower(coalesce(chunk_text, '')))"
)

FINAL_SCHEMA_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_documents_filename ON documents (filename)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_chunks_document_id_chunk_index ON chunks (document_id, chunk_index)",
    (
        "ALTER TABLE chunks "
        "ADD COLUMN IF NOT EXISTS search_vector tsvector "
        f"GENERATED ALWAYS AS ({SEARCH_VECTOR_GENERATED_EXPRESSION}) STORED"
    ),
    (
        f"CREATE INDEX IF NOT EXISTS {HNSW_CHUNK_EMBEDDING_INDEX_NAME} "
        "ON chunks USING hnsw (embedding vector_cosine_ops) "
        "WHERE embedding IS NOT NULL"
    ),
    (
        f"CREATE INDEX IF NOT EXISTS {SEARCH_VECTOR_GIN_INDEX_NAME} "
        "ON chunks USING gin (search_vector)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_chunks_chunk_text_trgm "
        "ON chunks USING gin (lower(chunk_text) gin_trgm_ops)"
    ),
    "ALTER TABLE chunks ALTER COLUMN metadata SET DEFAULT '{}'::jsonb",
    "UPDATE chunks SET metadata = '{}'::jsonb WHERE metadata IS NULL",
    "ALTER TABLE chunks ALTER COLUMN metadata SET NOT NULL",
)


async def prepare_database_schema(connection: AsyncConnection) -> None:
    """Create tables first, then apply idempotent schema refinements."""

    for statement in POSTGRES_EXTENSION_STATEMENTS:
        await connection.execute(text(statement))

    await connection.run_sync(Base.metadata.create_all)
    await _ensure_chunk_vector_dimension(connection)
    await _ensure_chunk_search_vector_config(connection)

    for statement in FINAL_SCHEMA_STATEMENTS:
        await connection.execute(text(statement))


async def _ensure_chunk_vector_dimension(connection: AsyncConnection) -> None:
    result = await connection.execute(
        text(
            """
            SELECT format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = 'chunks'
              AND a.attname = 'embedding'
              AND a.attnum > 0
              AND NOT a.attisdropped
            """
        )
    )
    raw_type = result.scalar_one_or_none()

    if not raw_type:
        return

    match = re.fullmatch(r"vector\((\d+)\)", raw_type)
    if not match:
        return

    current_dimension = int(match.group(1))
    target_dimension = settings.vector_size

    if current_dimension == target_dimension:
        return

    logger.warning(
        "Detected chunk embedding dimension %s but VECTOR_SIZE is %s. "
        "Existing embeddings will be cleared and the column will be resized. Re-embedding is required.",
        current_dimension,
        target_dimension,
    )
    await connection.execute(text(f"DROP INDEX IF EXISTS {HNSW_CHUNK_EMBEDDING_INDEX_NAME}"))
    await connection.execute(text("UPDATE chunks SET embedding = NULL WHERE embedding IS NOT NULL"))
    await connection.execute(
        text(f"ALTER TABLE chunks ALTER COLUMN embedding TYPE vector({target_dimension})")
    )


async def _ensure_chunk_search_vector_config(connection: AsyncConnection) -> None:
    result = await connection.execute(
        text(
            """
            SELECT pg_get_expr(ad.adbin, ad.adrelid)
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
            WHERE c.relname = 'chunks'
              AND a.attname = 'search_vector'
              AND a.attnum > 0
              AND NOT a.attisdropped
            """
        )
    )
    current_expression = result.scalar_one_or_none()

    if current_expression is None:
        return

    normalized_expression = current_expression.lower()
    target_expression = SEARCH_VECTOR_GENERATED_EXPRESSION.lower()

    if target_expression in normalized_expression:
        return

    if "to_tsvector(" not in normalized_expression:
        return

    logger.info(
        "Rebuilding chunks.search_vector to use PostgreSQL '%s' stemming.",
        POSTGRES_TEXT_SEARCH_CONFIG,
    )
    await connection.execute(text(f"DROP INDEX IF EXISTS {SEARCH_VECTOR_GIN_INDEX_NAME}"))
    await connection.execute(text("ALTER TABLE chunks DROP COLUMN IF EXISTS search_vector"))
    await connection.execute(
        text(
            "ALTER TABLE chunks "
            "ADD COLUMN search_vector tsvector "
            f"GENERATED ALWAYS AS ({SEARCH_VECTOR_GENERATED_EXPRESSION}) STORED"
        )
    )
