"""Request-scoped dependencies: DB session, authenticated user, and per-deal authorization."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, NotFoundError, PermissionDeniedError
from app.core.permissions import Permission, deal_permissions, role_permissions
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import Deal, DealMember, User
from app.repositories.deal_repository import DealRepository

SessionDep = Annotated[AsyncSession, Depends(get_session)]
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise AuthenticationError("Authentication required.")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AuthenticationError("Your session has expired. Please sign in again.") from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account not found or deactivated.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require(permission: Permission):
    """Global capability check (independent of any deal)."""

    async def checker(user: CurrentUser) -> User:
        if permission not in role_permissions(user.role):
            raise PermissionDeniedError("You do not have permission to perform this action.")
        return user

    return checker


@dataclass
class DealContext:
    deal: Deal
    user: User
    membership: DealMember | None
    permissions: frozenset[Permission]

    def require(self, permission: Permission) -> None:
        if permission not in self.permissions:
            raise PermissionDeniedError("Your role on this deal does not allow this action.")


async def get_deal_context(
    session: SessionDep, user: CurrentUser, deal_id: Annotated[uuid.UUID, Path()]
) -> DealContext:
    deal = await session.get(Deal, deal_id)
    if deal is None:
        raise NotFoundError("Deal not found.")
    membership = await DealRepository(session).get_membership(deal.id, user.id)
    if membership is None and not user.is_admin:
        # Do not reveal that the deal exists to non-members.
        raise NotFoundError("Deal not found.")
    return DealContext(
        deal=deal,
        user=user,
        membership=membership,
        permissions=deal_permissions(user.role, membership.member_role if membership else None),
    )


DealCtx = Annotated[DealContext, Depends(get_deal_context)]


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
