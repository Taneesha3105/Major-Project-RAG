"""Role-based access control.

Global role -> capabilities. Deal access additionally requires membership (admins see every deal),
and a deal "observer" membership downgrades any role to read-only on that deal.
"""

from enum import StrEnum

from app.models.enums import DealMemberRole, UserRole


class Permission(StrEnum):
    DEAL_CREATE = "deal:create"
    DEAL_EDIT = "deal:edit"
    DEAL_DELETE = "deal:delete"
    MEMBERS_MANAGE = "deal:members"
    DOCUMENT_UPLOAD = "document:upload"
    DOCUMENT_DELETE = "document:delete"
    CHAT = "chat:use"
    ANALYSIS_RUN = "analysis:run"
    FINDING_EDIT = "finding:edit"
    CHECKLIST_EDIT = "checklist:edit"
    AUDIT_VIEW = "audit:view"
    USER_MANAGE = "user:manage"
    USER_DIRECTORY = "user:directory"


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    UserRole.ADMIN: frozenset(Permission),
    UserRole.DEAL_LEAD: frozenset(Permission) - {Permission.USER_MANAGE},
    UserRole.ANALYST: frozenset(
        {
            Permission.DOCUMENT_UPLOAD,
            Permission.CHAT,
            Permission.ANALYSIS_RUN,
            Permission.FINDING_EDIT,
            Permission.CHECKLIST_EDIT,
            Permission.AUDIT_VIEW,
        }
    ),
    UserRole.VIEWER: frozenset({Permission.CHAT, Permission.AUDIT_VIEW}),
}

READ_ONLY_PERMISSIONS = frozenset({Permission.CHAT, Permission.AUDIT_VIEW})
# Managing the deal itself additionally requires being its lead (or an admin).
LEAD_ONLY_PERMISSIONS = frozenset({Permission.DEAL_EDIT, Permission.DEAL_DELETE, Permission.MEMBERS_MANAGE})


def role_permissions(role: UserRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def deal_permissions(role: UserRole, member_role: DealMemberRole | None) -> frozenset[Permission]:
    granted = role_permissions(role) - {Permission.USER_MANAGE, Permission.USER_DIRECTORY, Permission.DEAL_CREATE}
    if role == UserRole.ADMIN:
        return granted
    if member_role is None:
        return frozenset()
    if member_role == DealMemberRole.OBSERVER:
        return granted & READ_ONLY_PERMISSIONS
    if member_role != DealMemberRole.LEAD:
        granted -= LEAD_ONLY_PERMISSIONS
    return granted
