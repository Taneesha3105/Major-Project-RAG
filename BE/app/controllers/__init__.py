"""HTTP controllers (FastAPI routers). They validate input, enforce permissions and delegate to services."""

from fastapi import APIRouter

from app.controllers import (
    auth_controller,
    chat_controller,
    dashboard_controller,
    deal_controller,
    diligence_controller,
    document_controller,
    user_controller,
)

api_router = APIRouter()
for module in (
    auth_controller,
    user_controller,
    deal_controller,
    document_controller,
    chat_controller,
    diligence_controller,
    dashboard_controller,
):
    api_router.include_router(module.router)
