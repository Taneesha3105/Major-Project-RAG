from app.ai.retrieval import build_or_tsquery
from app.core.permissions import Permission, deal_permissions, role_permissions
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.enums import DealMemberRole, UserRole
from app.services.deal_service import readiness_score


def test_tsquery_drops_stopwords_and_special_characters():
    assert build_or_tsquery("What is the change-of-control clause in the M&A deal?") == "change | control | clause | deal"
    assert build_or_tsquery("what is it?") == ""


def test_password_hashing_and_tokens():
    hashed = hash_password("Secret123")
    assert verify_password("Secret123", hashed)
    assert not verify_password("wrong", hashed)
    token, expires_in = create_access_token("user-1", {"role": "analyst"})
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1" and payload["role"] == "analyst" and expires_in > 0


def test_role_permissions_hierarchy():
    assert Permission.USER_MANAGE in role_permissions(UserRole.ADMIN)
    assert Permission.USER_MANAGE not in role_permissions(UserRole.DEAL_LEAD)
    assert Permission.DOCUMENT_UPLOAD in role_permissions(UserRole.ANALYST)
    assert role_permissions(UserRole.VIEWER) == {Permission.CHAT, Permission.AUDIT_VIEW}


def test_deal_permissions_depend_on_membership():
    assert deal_permissions(UserRole.ANALYST, None) == frozenset()
    lead = deal_permissions(UserRole.DEAL_LEAD, DealMemberRole.LEAD)
    member = deal_permissions(UserRole.DEAL_LEAD, DealMemberRole.MEMBER)
    assert Permission.MEMBERS_MANAGE in lead and Permission.MEMBERS_MANAGE not in member
    assert deal_permissions(UserRole.DEAL_LEAD, DealMemberRole.OBSERVER) == {Permission.CHAT, Permission.AUDIT_VIEW}
    assert Permission.DEAL_DELETE in deal_permissions(UserRole.ADMIN, None)


def test_readiness_score_bounds():
    assert readiness_score({}) == 0
    perfect = {"checklist_total": 10, "checklist_completed": 10, "ready_document_count": 6}
    assert readiness_score(perfect, {"financial", "legal", "tax", "contracts", "hr", "corporate"}) == 100
    risky = dict(perfect, open_risk_count=5, critical_risk_count=4)
    assert readiness_score(risky, {"financial"}) < readiness_score(perfect, {"financial"})
