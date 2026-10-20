import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.controllers.deps import SessionDep, require
from app.core.permissions import Permission
from app.models import User
from app.schemas.user import UserAdminUpdate, UserCreate, UserRead
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=list[UserRead])
async def list_users(
    session: SessionDep,
    _: Annotated[User, Depends(require(Permission.USER_DIRECTORY))],
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[User]:
    return await UserService(session).list_users(q)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate, session: SessionDep, actor: Annotated[User, Depends(require(Permission.USER_MANAGE))]
) -> User:
    return await UserService(session).create_user(actor, payload)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserAdminUpdate,
    session: SessionDep,
    actor: Annotated[User, Depends(require(Permission.USER_MANAGE))],
) -> User:
    return await UserService(session).admin_update(actor, user_id, payload)
