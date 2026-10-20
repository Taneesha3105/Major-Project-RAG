from fastapi import APIRouter

from app.controllers.deps import CurrentUser, SessionDep
from app.schemas.dashboard import DashboardSummary, SystemStatus
from app.services.dashboard_service import DashboardService

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", response_model=DashboardSummary)
async def dashboard(user: CurrentUser, session: SessionDep) -> DashboardSummary:
    return await DashboardService(session).summary(user)


@router.get("/system/status", response_model=SystemStatus)
async def system_status(_: CurrentUser, session: SessionDep) -> SystemStatus:
    return await DashboardService(session).system_status()
