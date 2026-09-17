import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.db.schema import (
    HNSW_CHUNK_EMBEDDING_INDEX_NAME,
    POSTGRES_TEXT_SEARCH_CONFIG,
    SEARCH_VECTOR_GIN_INDEX_NAME,
    prepare_database_schema,
)


class SchemaHnswTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_database_schema_enables_pg_trgm_and_creates_chunk_text_index(self):
        connection = AsyncMock()
        scalar_result = Mock()
        scalar_result.scalar_one_or_none.return_value = "vector(384)"
        connection.execute = AsyncMock(return_value=scalar_result)
        connection.run_sync = AsyncMock()

        with patch("app.db.schema.settings.vector_size", 384):
            await prepare_database_schema(connection)

        executed_sql = [str(call.args[0]) for call in connection.execute.await_args_list]

        self.assertTrue(
            any("CREATE EXTENSION IF NOT EXISTS pg_trgm" in statement for statement in executed_sql)
        )
        self.assertTrue(
            any(
                "CREATE INDEX IF NOT EXISTS ix_chunks_chunk_text_trgm" in statement
                and "USING gin" in statement
                and "lower(chunk_text) gin_trgm_ops" in statement
                for statement in executed_sql
            )
        )

    async def test_prepare_database_schema_creates_search_vector_column_and_index(self):
        connection = AsyncMock()
        scalar_result = Mock()
        scalar_result.scalar_one_or_none.return_value = "vector(384)"
        connection.execute = AsyncMock(return_value=scalar_result)
        connection.run_sync = AsyncMock()

        with patch("app.db.schema.settings.vector_size", 384):
            await prepare_database_schema(connection)

        executed_sql = [str(call.args[0]) for call in connection.execute.await_args_list]

        self.assertTrue(
            any(
                "ADD COLUMN IF NOT EXISTS search_vector tsvector" in statement
                and "GENERATED ALWAYS AS" in statement
                and f"to_tsvector('{POSTGRES_TEXT_SEARCH_CONFIG}'" in statement
                for statement in executed_sql
            )
        )
        self.assertTrue(
            any(
                f"CREATE INDEX IF NOT EXISTS {SEARCH_VECTOR_GIN_INDEX_NAME}" in statement
                and "USING gin (search_vector)" in statement
                for statement in executed_sql
            )
        )

    async def test_prepare_database_schema_rebuilds_old_simple_search_vector(self):
        connection = AsyncMock()
        vector_result = Mock()
        vector_result.scalar_one_or_none.return_value = "vector(384)"
        search_vector_result = Mock()
        search_vector_result.scalar_one_or_none.return_value = (
            "to_tsvector('simple'::regconfig, lower(COALESCE(chunk_text, ''::text)))"
        )
        default_result = Mock()

        async def execute_side_effect(statement):
            sql = str(statement)
            if "SELECT format_type" in sql:
                return vector_result
            if "SELECT pg_get_expr" in sql:
                return search_vector_result
            return default_result

        connection.execute = AsyncMock(side_effect=execute_side_effect)
        connection.run_sync = AsyncMock()

        with patch("app.db.schema.settings.vector_size", 384):
            await prepare_database_schema(connection)

        executed_sql = [str(call.args[0]) for call in connection.execute.await_args_list]

        self.assertIn(f"DROP INDEX IF EXISTS {SEARCH_VECTOR_GIN_INDEX_NAME}", executed_sql)
        self.assertIn("ALTER TABLE chunks DROP COLUMN IF EXISTS search_vector", executed_sql)
        self.assertTrue(
            any(
                "ALTER TABLE chunks ADD COLUMN search_vector tsvector" in statement
                and f"to_tsvector('{POSTGRES_TEXT_SEARCH_CONFIG}'" in statement
                for statement in executed_sql
            )
        )

    async def test_prepare_database_schema_creates_partial_hnsw_index(self):
        connection = AsyncMock()
        scalar_result = Mock()
        scalar_result.scalar_one_or_none.return_value = "vector(384)"
        connection.execute = AsyncMock(return_value=scalar_result)
        connection.run_sync = AsyncMock()

        with patch("app.db.schema.settings.vector_size", 384):
            await prepare_database_schema(connection)

        executed_sql = [str(call.args[0]) for call in connection.execute.await_args_list]

        self.assertTrue(
            any(
                f"CREATE INDEX IF NOT EXISTS {HNSW_CHUNK_EMBEDDING_INDEX_NAME}" in statement
                and "USING hnsw" in statement
                and "vector_cosine_ops" in statement
                and "WHERE embedding IS NOT NULL" in statement
                for statement in executed_sql
            )
        )

    async def test_prepare_database_schema_drops_hnsw_index_before_resizing_vector_column(self):
        connection = AsyncMock()
        scalar_result = Mock()
        scalar_result.scalar_one_or_none.return_value = "vector(768)"
        connection.execute = AsyncMock(return_value=scalar_result)
        connection.run_sync = AsyncMock()

        with patch("app.db.schema.settings.vector_size", 384):
            await prepare_database_schema(connection)

        executed_sql = [str(call.args[0]) for call in connection.execute.await_args_list]

        drop_index_position = executed_sql.index(f"DROP INDEX IF EXISTS {HNSW_CHUNK_EMBEDDING_INDEX_NAME}")
        alter_column_position = executed_sql.index("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(384)")

        self.assertLess(drop_index_position, alter_column_position)


if __name__ == "__main__":
    unittest.main()
