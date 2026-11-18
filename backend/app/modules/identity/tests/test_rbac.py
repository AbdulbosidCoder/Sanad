import pytest
from fastapi import Depends

from app.core.auth import Principal, require_permission
from app.core.db import get_sessionmaker
from app.core.errors import AppError
from app.core.modules import module_router
from app.modules.identity import service
from app.modules.identity.rbac import PERMISSIONS, ROLES_BY_CODE
from app.modules.identity.tests.helpers import API, register

pytestmark = pytest.mark.usefixtures("database")


def _mount_protected(app) -> None:
    router = module_router("identity")

    @router.get("/_test/block-users")
    async def protected(
        p: Principal = Depends(require_permission("users.block")),
    ) -> dict[str, str]:
        return {"user": str(p.user_id)}

    app.include_router(router, prefix=API)


async def _grant(email: str, role: str) -> None:
    async with get_sessionmaker()() as db:
        user_id = await service.find_user_id(db, email)
        assert user_id is not None
        await service.grant_role(db, user_id, role)


async def test_permission_is_checked_and_role_changes_apply_immediately(app, client):
    _mount_protected(app)
    me, payload = await register(client)

    denied = await client.get(f"{API}/_test/block-users", headers=me.auth)
    assert denied.status_code == 403
    assert denied.json()["code"] == "IDENTITY.FORBIDDEN"

    await _grant(str(payload["email"]), "admin")
    # Same access token: rights are read from the database on every request.
    allowed = await client.get(f"{API}/_test/block-users", headers=me.auth)
    assert allowed.status_code == 200

    profile = (await client.get(f"{API}/me", headers=me.auth)).json()
    assert set(profile["roles"]) == {"customer", "admin"}
    assert "users.block" in profile["permissions"]
    assert "rbac.manage" not in profile["permissions"]  # super_admin only


async def test_super_admin_has_every_permission(client):
    me, payload = await register(client)
    await _grant(str(payload["email"]), "super_admin")
    profile = (await client.get(f"{API}/me", headers=me.auth)).json()
    assert set(profile["permissions"]) == set(PERMISSIONS)


async def test_store_roles_cannot_be_granted_as_platform_roles(client):
    _, payload = await register(client)
    with pytest.raises(AppError) as exc:
        await _grant(str(payload["email"]), "seller_owner")
    assert exc.value.code == "STORE_ROLE"


async def test_sync_is_idempotent():
    async with get_sessionmaker()() as db:
        await service.sync_rbac(db)
        await service.sync_rbac(db)
        await db.commit()


def test_catalog_matches_the_matrix():
    assert ROLES_BY_CODE["customer"].permissions == frozenset()
    assert "refunds.approve" in ROLES_BY_CODE["finance"].permissions
    # Separation of duties: support can initiate a refund but never approve it.
    assert "refunds.approve" not in ROLES_BY_CODE["support_lead"].permissions
    assert "refunds.initiate" in ROLES_BY_CODE["support_lead"].permissions
    # Developers never see personal data.
    assert not {"users.read", "orders.read"} & ROLES_BY_CODE["developer"].permissions
