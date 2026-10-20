import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.controllers.deps import DealCtx, SessionDep
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.models import DocumentChunk
from app.models.enums import DocumentCategory, DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import ChunkRead, DocumentRead, DocumentUpdate, UploadResult
from app.services.document_service import DocumentService, to_read

router = APIRouter(prefix="/deals/{deal_id}/documents", tags=["Documents"])


@router.get("", response_model=list[DocumentRead])
async def list_documents(
    ctx: DealCtx,
    session: SessionDep,
    category: DocumentCategory | None = None,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> list[DocumentRead]:
    return await DocumentService(session).list(ctx.deal, category, status_filter, search)


@router.post("", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload_documents(
    ctx: DealCtx,
    session: SessionDep,
    files: Annotated[list[UploadFile], File(description="One or more documents")],
    category: Annotated[DocumentCategory, Form()] = DocumentCategory.OTHER,
    description: Annotated[str | None, Form(max_length=2000)] = None,
) -> UploadResult:
    ctx.require(Permission.DOCUMENT_UPLOAD)
    return await DocumentService(session).upload(ctx.user, ctx.deal, files, category, description)


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: uuid.UUID, ctx: DealCtx, session: SessionDep) -> DocumentRead:
    return to_read(await DocumentService(session).get(ctx.deal, document_id))


@router.patch("/{document_id}", response_model=DocumentRead)
async def update_document(
    document_id: uuid.UUID, payload: DocumentUpdate, ctx: DealCtx, session: SessionDep
) -> DocumentRead:
    ctx.require(Permission.DOCUMENT_UPLOAD)
    return await DocumentService(session).update(ctx.user, ctx.deal, document_id, payload)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, ctx: DealCtx, session: SessionDep) -> Response:
    ctx.require(Permission.DOCUMENT_DELETE)
    await DocumentService(session).delete(ctx.user, ctx.deal, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{document_id}/reprocess", response_model=DocumentRead)
async def reprocess_document(document_id: uuid.UUID, ctx: DealCtx, session: SessionDep) -> DocumentRead:
    ctx.require(Permission.DOCUMENT_UPLOAD)
    return await DocumentService(session).reprocess(ctx.user, ctx.deal, document_id)


@router.get("/{document_id}/download")
async def download_document(document_id: uuid.UUID, ctx: DealCtx, session: SessionDep) -> FileResponse:
    service = DocumentService(session)
    document = await service.get(ctx.deal, document_id)
    path = service.file_path(document)
    if not path.exists():
        raise NotFoundError("The stored file is missing.")
    return FileResponse(
        path,
        media_type=document.mime_type or "application/octet-stream",
        filename=document.filename,
        content_disposition_type="inline",
    )


@router.get("/{document_id}/chunks", response_model=list[ChunkRead])
async def list_chunks(
    document_id: uuid.UUID,
    ctx: DealCtx,
    session: SessionDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[DocumentChunk]:
    await DocumentService(session).get(ctx.deal, document_id)
    return list(await DocumentRepository(session).list_chunks(document_id, offset, limit))
