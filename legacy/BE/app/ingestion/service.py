from __future__ import annotations

import hashlib
import logging
import re

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Chunk, Document
from app.embeddings.service import DocumentEmbeddingService
from app.ingestion.chunker import IngestionChunk, split_parsed_document_into_chunks, split_text_into_chunks
from app.ingestion.parsers import DocumentParseError, ParsedDocument, parse_uploaded_document
from app.ingestion.schemas import DocumentIngestResponse

logger = logging.getLogger(__name__)


class DocumentIngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.embedding_service = DocumentEmbeddingService(session)

    async def ingest_text(
        self,
        text: str,
        filename: str,
        source_type: str,
        *,
        source_format: str | None = None,
        parser_name: str | None = None,
        content_hash: str | None = None,
    ) -> DocumentIngestResponse:
        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("Text content cannot be empty.")

        chunk_rows = split_text_into_chunks(
            text=cleaned_text,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

        if not chunk_rows:
            raise ValueError("Unable to create chunks from the provided content.")

        resolved_content_hash = content_hash or self._generate_content_hash_from_text(cleaned_text)
        resolved_source_format = source_format or "text"
        resolved_parser_name = parser_name or "plain_text"

        return await self._store_document_chunks(
            filename=filename,
            content_hash=resolved_content_hash,
            source_type=source_type,
            source_format=resolved_source_format,
            parser_name=resolved_parser_name,
            chunks=chunk_rows,
            parser_mode="plain_text",
        )

    async def ingest_file(self, content: bytes, filename: str, source_type: str = "file") -> DocumentIngestResponse:
        if not content:
            raise ValueError("Uploaded file is empty.")

        parsed_document = parse_uploaded_document(content, filename)
        content_hash = self._generate_content_hash_from_bytes(content)

        if parsed_document.source_format in {"pdf", "docx"}:
            chunks = split_parsed_document_into_chunks(
                parsed_document=parsed_document,
                chunk_size=settings.chunk_size,
            )
            chunks = self._filter_low_information_parsed_chunks(chunks)
            if not chunks:
                raise ValueError("Unable to create chunks from the parsed document.")

            return await self._store_document_chunks(
                filename=filename,
                content_hash=content_hash,
                source_type=source_type,
                source_format=parsed_document.source_format,
                parser_name=parsed_document.parser_name,
                chunks=chunks,
                parser_mode=str(parsed_document.parse_metadata.get("parser_mode", "structured")),
            )

        return await self.ingest_text(
            text=parsed_document.normalized_text,
            filename=filename,
            source_type=source_type,
            source_format=parsed_document.source_format,
            parser_name=parsed_document.parser_name,
            content_hash=content_hash,
        )

    async def _store_document_chunks(
        self,
        *,
        filename: str,
        content_hash: str,
        source_type: str,
        source_format: str,
        parser_name: str,
        chunks: list[IngestionChunk],
        parser_mode: str,
    ) -> DocumentIngestResponse:
        existing_document = await self._get_document_by_hash(content_hash)
        if existing_document is not None:
            chunk_count = await self._count_document_chunks(existing_document.id)
            logger.info("Duplicate document detected for hash %s. Skipping ingestion.", content_hash)
            return DocumentIngestResponse(
                document_id=existing_document.id,
                filename=existing_document.filename,
                content_hash=existing_document.content_hash,
                chunk_count=chunk_count,
                duplicate=True,
                source_type=source_type,
                source_format=source_format,
                parser_name=parser_name,
                message="Duplicate document detected. Existing record returned.",
            )

        document = Document(filename=filename, content_hash=content_hash)

        try:
            self.session.add(document)
            await self.session.flush()

            embeddings = await self.embedding_service.generate_embeddings([chunk.text for chunk in chunks])
            embedding_metadata = self.embedding_service.build_embedding_metadata()

            chunk_rows = []
            for chunk, embedding in zip(chunks, embeddings):
                chunk_metadata = {
                    "source_type": source_type,
                    "source_format": source_format,
                    "parser_name": parser_name,
                    "parser_mode": parser_mode,
                    "start_char": chunk.start_char,
                    "end_char": chunk.end_char,
                    **self._build_structure_metadata(chunk.text),
                    **chunk.metadata,
                    **embedding_metadata,
                }

                chunk_rows.append(
                    Chunk(
                        document_id=document.id,
                        chunk_index=chunk.index,
                        chunk_text=chunk.text,
                        embedding=embedding,
                        chunk_metadata=chunk_metadata,
                    )
                )

            self.session.add_all(chunk_rows)
            await self.session.commit()
            await self.session.refresh(document)
        except IntegrityError:
            await self.session.rollback()
            logger.warning("Concurrent duplicate detected for hash %s.", content_hash)
            existing_document = await self._get_document_by_hash(content_hash)
            if existing_document is None:
                raise ValueError("Document ingestion failed because the content already exists.")

            chunk_count = await self._count_document_chunks(existing_document.id)
            return DocumentIngestResponse(
                document_id=existing_document.id,
                filename=existing_document.filename,
                content_hash=existing_document.content_hash,
                chunk_count=chunk_count,
                duplicate=True,
                source_type=source_type,
                source_format=source_format,
                parser_name=parser_name,
                message="Duplicate document detected. Existing record returned.",
            )
        except Exception:
            await self.session.rollback()
            raise

        logger.info("Document %s stored with %s chunks.", document.id, len(chunks))
        return DocumentIngestResponse(
            document_id=document.id,
            filename=document.filename,
            content_hash=document.content_hash,
            chunk_count=len(chunks),
            duplicate=False,
            source_type=source_type,
            source_format=source_format,
            parser_name=parser_name,
            message=(
                "Document ingested successfully and embeddings were stored "
                f"using {self.embedding_service.provider.display_name}."
            ),
        )

    async def _get_document_by_hash(self, content_hash: str) -> Document | None:
        statement = select(Document).where(Document.content_hash == content_hash)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def _count_document_chunks(self, document_id: int) -> int:
        statement = select(func.count(Chunk.id)).where(Chunk.document_id == document_id)
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    @staticmethod
    def _generate_content_hash_from_text(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_content_hash_from_bytes(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @classmethod
    def _build_structure_metadata(cls, chunk_text: str) -> dict[str, object]:
        section_anchor = cls._extract_section_anchor(chunk_text)
        table_like_row = cls._looks_table_like(chunk_text)
        label_value_row = cls._looks_label_value_row(chunk_text)
        line_kind = "table_like" if table_like_row else "label_value" if label_value_row else "narrative"
        sentence_offsets = cls._extract_sentence_offsets(chunk_text)

        return {
            "heading_path": [section_anchor] if section_anchor else [],
            "section_anchor": section_anchor,
            "line_kind": line_kind,
            "sentence_offsets": sentence_offsets,
            "table_like_row": table_like_row,
            "label_value_row": label_value_row,
        }

    @staticmethod
    def _filter_low_information_parsed_chunks(chunks: list[IngestionChunk]) -> list[IngestionChunk]:
        filtered_chunks = [
            chunk
            for chunk in chunks
            if not DocumentIngestionService._is_low_information_parsed_chunk(chunk)
        ]

        for index, chunk in enumerate(filtered_chunks):
            chunk.index = index

        return filtered_chunks

    @staticmethod
    def _is_low_information_parsed_chunk(chunk: IngestionChunk) -> bool:
        text = chunk.text.strip()
        if not text:
            return True

        normalized_lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in text.replace("\r\n", "\n").split("\n")
            if re.sub(r"\s+", " ", line).strip()
        ]
        word_count = len(re.findall(r"[A-Za-z0-9']+", text))

        if ".com" in text.lower() and word_count <= 10 and len(normalized_lines) <= 3:
            return True

        if word_count <= 6 and len(normalized_lines) >= 2 and all(len(line) <= 24 for line in normalized_lines):
            return True

        if word_count <= 4 and len(normalized_lines) >= 2:
            return True

        return False

    @staticmethod
    def _extract_section_anchor(chunk_text: str) -> str | None:
        for raw_line in chunk_text.replace("\r\n", "\n").split("\n"):
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            if len(line) > 120:
                continue
            if line.startswith(("â€¢", "-", "*")):
                continue
            if re.search(r"\b(section|chapter)\b", line, re.IGNORECASE):
                return line
            if "." not in line and re.match(r"^[A-Z0-9][A-Za-z0-9 /&()'-]+$", line):
                return line
        return None

    @staticmethod
    def _extract_sentence_offsets(chunk_text: str) -> list[int]:
        offsets = [0]
        for match in re.finditer(r"(?<=[.!?])\s+", chunk_text):
            offsets.append(match.end())
        return sorted(set(offset for offset in offsets if offset < len(chunk_text)))

    @staticmethod
    def _looks_table_like(chunk_text: str) -> bool:
        normalized_lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in chunk_text.replace("\r\n", "\n").split("\n")
            if line.strip()
        ]
        if len(normalized_lines) < 2:
            return False
        numeric_or_value_lines = sum(
            1
            for line in normalized_lines
            if any(marker in line for marker in ("$", "%", ":"))
            or bool(re.search(r"\b\d+\b", line))
        )
        return numeric_or_value_lines >= 2

    @staticmethod
    def _looks_label_value_row(chunk_text: str) -> bool:
        single_line = re.sub(r"\s+", " ", chunk_text).strip()
        if not single_line:
            return False
        if ":" in single_line:
            return True
        return bool(
            re.match(r"^[A-Za-z][A-Za-z0-9 /&()'-]{3,}\s+[$\d%][A-Za-z0-9 $%.,()-]*$", single_line)
        )


__all__ = ["DocumentIngestionService", "DocumentParseError", "ParsedDocument"]
