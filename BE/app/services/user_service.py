import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.core.permissions import role_permissions
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.models.enums import UserRole
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenResponse
from app.schemas.user import PasswordChange, UserAdminUpdate, UserCreate, UserRead, UserRegister, UserUpdateMe
from app.services.audit_service import AuditService


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)
        self.audit = AuditService(session)

    # --- authentication ---
    async def register(self, payload: UserRegister, ip: str | None = None) -> TokenResponse:
        role = UserRole(settings.default_signup_role) if settings.default_signup_role in UserRole else UserRole.ANALYST
        if role == UserRole.ADMIN:
            role = UserRole.ANALYST  # never allow self-service admin accounts
        user = await self._create(payload, role)
        await self.audit.log(
            action="user.registered", entity_type="user", entity_id=user.id, user=user,
            summary=f"{user.full_name} created an account", ip_address=ip,
        )
        token = self._issue_token(user)
        await self.session.commit()
        return token

    async def login(self, email: str, password: str, ip: str | None = None) -> TokenResponse:
        user = await self.repo.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise AuthenticationError("Incorrect email or password.")
        if not user.is_active:
            raise AuthenticationError("This account has been deactivated. Contact your administrator.")
        user.last_login_at = datetime.now(UTC)
        await self.audit.log(
            action="user.login", entity_type="user", entity_id=user.id, user=user,
            summary=f"{user.full_name} signed in", ip_address=ip,
        )
        token = self._issue_token(user)
        await self.session.commit()
        return token

    @staticmethod
    def _issue_token(user: User) -> TokenResponse:
        token, expires_in = create_access_token(str(user.id), {"role": user.role.value})
        return TokenResponse(access_token=token, expires_in=expires_in, user=UserRead.model_validate(user))

    @staticmethod
    def permissions_for(user: User) -> list[str]:
        return sorted(permission.value for permission in role_permissions(user.role))

    # --- profile ---
    async def update_me(self, user: User, payload: UserUpdateMe) -> User:
        self.repo.apply_updates(user, payload.model_dump(exclude_unset=True))
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def change_password(self, user: User, payload: PasswordChange) -> None:
        if not verify_password(payload.current_password, user.hashed_password):
            raise ValidationFailedError("Current password is incorrect.")
        user.hashed_password = hash_password(payload.new_password)
        await self.audit.log(action="user.password_changed", entity_type="user", entity_id=user.id, user=user,
                             summary=f"{user.full_name} changed their password")
        await self.session.commit()

    # --- administration ---
    async def list_users(self, query: str | None) -> list[User]:
        return list(await self.repo.search(query))

    async def create_user(self, actor: User, payload: UserCreate) -> User:
        user = await self._create(payload, payload.role)
        await self.audit.log(action="user.created", entity_type="user", entity_id=user.id, user=actor,
                             summary=f"{actor.full_name} created user {user.email} ({user.role.value})")
        await self.session.commit()
        return user

    async def admin_update(self, actor: User, user_id: uuid.UUID, payload: UserAdminUpdate) -> User:
        user = await self.repo.get(user_id)
        if user is None:
            raise NotFoundError("User not found.")
        changes = payload.model_dump(exclude_unset=True)
        if user.id == actor.id and (changes.get("role") not in (None, UserRole.ADMIN) or changes.get("is_active") is False):
            raise PermissionDeniedError("You cannot remove your own administrator access.")
        self.repo.apply_updates(user, changes)
        await self.audit.log(action="user.updated", entity_type="user", entity_id=user.id, user=actor,
                             summary=f"{actor.full_name} updated {user.email}",
                             details={k: str(v) for k, v in changes.items()})
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def _create(self, payload: UserRegister, role: UserRole) -> User:
        if await self.repo.get_by_email(payload.email):
            raise ConflictError("An account with this email already exists.")
        return await self.repo.add(
            User(
                email=payload.email.lower(),
                full_name=payload.full_name.strip(),
                hashed_password=hash_password(payload.password),
                role=role,
                job_title=payload.job_title,
                organization=payload.organization,
            )
        )
