import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.controllers.deps import DealCtx, SessionDep
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.models import AnalysisRun, ChecklistItem, RiskFinding
from app.models.enums import DocumentCategory, FindingStatus, FindingType, Severity
from app.schemas.diligence import (
    AnalysisRequest,
    AnalysisRunRead,
    ChecklistItemCreate,
    ChecklistItemRead,
    ChecklistItemUpdate,
    ChecklistReviewResult,
    RiskFindingCreate,
    RiskFindingRead,
    RiskFindingUpdate,
)
from app.services.analysis_service import AnalysisService, review_checklist
from app.services.diligence_service import ChecklistService, RiskService

router = APIRouter(prefix="/deals/{deal_id}", tags=["Due Diligence"])


# --- Checklist -----------------------------------------------------------------
@router.get("/checklist", response_model=list[ChecklistItemRead])
async def list_checklist(ctx: DealCtx, session: SessionDep) -> list[ChecklistItem]:
    return await ChecklistService(session).list(ctx.deal)


@router.post("/checklist", response_model=ChecklistItemRead, status_code=status.HTTP_201_CREATED)
async def create_checklist_item(payload: ChecklistItemCreate, ctx: DealCtx, session: SessionDep) -> ChecklistItem:
    ctx.require(Permission.CHECKLIST_EDIT)
    return await ChecklistService(session).create(ctx.user, ctx.deal, payload)


@router.patch("/checklist/{item_id}", response_model=ChecklistItemRead)
async def update_checklist_item(
    item_id: uuid.UUID, payload: ChecklistItemUpdate, ctx: DealCtx, session: SessionDep
) -> ChecklistItem:
    ctx.require(Permission.CHECKLIST_EDIT)
    return await ChecklistService(session).update(ctx.user, ctx.deal, item_id, payload)


@router.delete("/checklist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_checklist_item(item_id: uuid.UUID, ctx: DealCtx, session: SessionDep) -> Response:
    ctx.require(Permission.CHECKLIST_EDIT)
    await ChecklistService(session).delete(ctx.user, ctx.deal, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/checklist/ai-review", response_model=ChecklistReviewResult)
async def ai_review_checklist(ctx: DealCtx, session: SessionDep) -> ChecklistReviewResult:
    ctx.require(Permission.ANALYSIS_RUN)
    return ChecklistReviewResult(**await review_checklist(session, ctx.user, ctx.deal))


# --- Risk register -------------------------------------------------------------
@router.get("/risks", response_model=list[RiskFindingRead])
async def list_risks(
    ctx: DealCtx,
    session: SessionDep,
    severity: Severity | None = None,
    status_filter: Annotated[FindingStatus | None, Query(alias="status")] = None,
    finding_type: FindingType | None = None,
    category: DocumentCategory | None = None,
) -> list[RiskFinding]:
    return await RiskService(session).list(ctx.deal, severity, status_filter, finding_type, category)


@router.post("/risks", response_model=RiskFindingRead, status_code=status.HTTP_201_CREATED)
async def create_risk(payload: RiskFindingCreate, ctx: DealCtx, session: SessionDep) -> RiskFinding:
    ctx.require(Permission.FINDING_EDIT)
    return await RiskService(session).create(ctx.user, ctx.deal, payload)


@router.patch("/risks/{finding_id}", response_model=RiskFindingRead)
async def update_risk(
    finding_id: uuid.UUID, payload: RiskFindingUpdate, ctx: DealCtx, session: SessionDep
) -> RiskFinding:
    ctx.require(Permission.FINDING_EDIT)
    return await RiskService(session).update(ctx.user, ctx.deal, finding_id, payload)


@router.delete("/risks/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_risk(finding_id: uuid.UUID, ctx: DealCtx, session: SessionDep) -> Response:
    ctx.require(Permission.FINDING_EDIT)
    await RiskService(session).delete(ctx.user, ctx.deal, finding_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- AI analysis runs ----------------------------------------------------------
@router.post("/analysis", response_model=AnalysisRunRead, status_code=status.HTTP_202_ACCEPTED)
async def start_analysis(payload: AnalysisRequest, ctx: DealCtx, session: SessionDep) -> AnalysisRun:
    ctx.require(Permission.ANALYSIS_RUN)
    return await AnalysisService(session).start(
        ctx.user, ctx.deal, payload.categories, payload.replace_previous_ai_findings
    )


@router.get("/analysis", response_model=list[AnalysisRunRead])
async def list_analysis_runs(ctx: DealCtx, session: SessionDep) -> list[AnalysisRun]:
    return await AnalysisService(session).list_runs(ctx.deal)


@router.get("/analysis/{run_id}", response_model=AnalysisRunRead)
async def get_analysis_run(run_id: uuid.UUID, ctx: DealCtx, session: SessionDep) -> AnalysisRun:
    run = await AnalysisService(session).get_run(ctx.deal, run_id)
    if run is None:
        raise NotFoundError("Analysis run not found.")
    return run
