from fastapi import APIRouter, Request, status

from app.controllers.deps import CurrentUser, SessionDep, client_ip
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.common import Message
from app.schemas.user import PasswordChange, UserRead, UserRegister, UserUpdateMe
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Authentication"])


class MeResponse(UserRead):
    permissions: list[str]


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, request: Request, session: SessionDep) -> TokenResponse:
    return await UserService(session).register(payload, client_ip(request))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, session: SessionDep) -> TokenResponse:
    return await UserService(session).login(payload.email, payload.password, client_ip(request))


@router.get("/me", response_model=MeResponse)
async def me(user: CurrentUser) -> MeResponse:
    return MeResponse(**UserRead.model_validate(user).model_dump(), permissions=UserService.permissions_for(user))


@router.patch("/me", response_model=MeResponse)
async def update_me(payload: UserUpdateMe, user: CurrentUser, session: SessionDep) -> MeResponse:
    updated = await UserService(session).update_me(user, payload)
    return MeResponse(**UserRead.model_validate(updated).model_dump(), permissions=UserService.permissions_for(updated))


@router.post("/change-password", response_model=Message)
async def change_password(payload: PasswordChange, user: CurrentUser, session: SessionDep) -> Message:
    await UserService(session).change_password(user, payload)
    return Message(message="Password updated.")
