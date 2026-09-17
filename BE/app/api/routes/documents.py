import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db_session
from app.documents.schemas import DocumentDeleteResponse, DocumentDetailResponse, DocumentListResponse
from app.documents.service import DocumentManagementService
from app.embeddings.provider import EmbeddingProviderError
from app.embeddings.schemas import EmbeddingGenerationResponse
from app.embeddings.service import DocumentEmbeddingService
from app.ingestion.schemas import DocumentIngestResponse, TextIngestRequest
from app.ingestion.service import DocumentIngestionService, DocumentParseError

router = APIRouter(prefix="/documents", tags=["documents"])
logger = logging.getLogger(__name__)


@router.get("", response_model=DocumentListResponse, status_code=status.HTTP_200_OK)
async def list_documents(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentListResponse:
    service = DocumentManagementService(session)

    try:
        return await service.list_documents()
    except Exception as exc:
        logger.exception("Unexpected error while listing documents.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while listing documents.",
        ) from exc


@router.get("/{document_id}", response_model=DocumentDetailResponse, status_code=status.HTTP_200_OK)
async def get_document_details(
    document_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> DocumentDetailResponse:
    service = DocumentManagementService(session)

    try:
        return await service.get_document_detail(document_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error while loading document details.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while loading the document.",
        ) from exc


@router.delete("/{document_id}", response_model=DocumentDeleteResponse, status_code=status.HTTP_200_OK)
async def delete_document(
    document_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> DocumentDeleteResponse:
    service = DocumentManagementService(session)

    try:
        return await service.delete_document(document_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error while deleting document %s.", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while deleting the document.",
        ) from exc


@router.post("/ingest/text", response_model=DocumentIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_text_document(
    payload: TextIngestRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> DocumentIngestResponse:
    service = DocumentIngestionService(session)

    try:
        result = await service.ingest_text(
            text=payload.text,
            filename=payload.filename or settings.default_text_filename,
            source_type="text",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error while ingesting text document.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while ingesting the document.",
        ) from exc

    if result.duplicate:
        response.status_code = status.HTTP_200_OK

    return result


@router.post(
    "/{document_id}/embeddings",
    response_model=EmbeddingGenerationResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_document_embeddings(
    document_id: int,
    force: bool = False,
    session: AsyncSession = Depends(get_db_session),
) -> EmbeddingGenerationResponse:
    service = DocumentEmbeddingService(session)

    try:
        return await service.embed_document_chunks(document_id, force=force)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error while generating document embeddings.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while generating embeddings.",
        ) from exc


@router.post("/ingest/file", response_model=DocumentIngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_file_document(
    response: Response,
    file: UploadFile = File(...),
    filename: str | None = Form(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentIngestResponse:
    if not file.filename and not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A filename is required for uploaded content.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    service = DocumentIngestionService(session)

    try:
        result = await service.ingest_file(
            content=content,
            filename=filename or file.filename or settings.default_text_filename,
        )
    except (ValueError, DocumentParseError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error while ingesting file document.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while ingesting the document.",
        ) from exc

    if result.duplicate:
        response.status_code = status.HTTP_200_OK

    return result
