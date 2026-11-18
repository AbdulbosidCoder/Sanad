"""Built-in roles and permissions: the code form of docs/architecture/04-rbac-matrix.md.

This catalog is the single source of truth. ``service.sync_rbac`` writes it to the database
on every startup (idempotent), so changing a role here and restarting is all it takes.
Roles created later by a super admin through the API are not touched by the sync.

Resources marked 👤 in the matrix ("only your own": cart, own orders, own tickets) need no
permission: any signed-in user may act on their own objects, and services check ownership.
Store roles are granted per store through ``StoreMembership`` (stores module), not ``user_roles``.
"""

from dataclasses import dataclass
from typing import Literal

PERMISSIONS: dict[str, str] = {
    # Catalog
    "products.write": "Create, edit and archive products",
    "products.delete": "Delete products",
    "products.moderate": "Moderate any product on the platform",
    "inventory.write": "Change stock levels",
    "catalog.manage": "Manage categories and brands",
    # Orders, returns, money
    "orders.read": "View all orders",
    "orders.read_ticket": "View orders linked to an assigned support ticket",
    "orders.seller_manage": "Process the store's orders and change their status",
    "orders.status_override": "Change any order status as platform staff",
    "returns.decide": "Approve or reject product returns",
    "refunds.initiate": "Initiate a money refund",
    "refunds.approve": "Approve and execute a money refund",
    "payments.read": "View payments and transactions",
    # Stores
    "store.analytics_read": "View store analytics",
    "store.finance_read": "View store revenue and commission",
    "store.staff_manage": "Manage store staff",
    "store.settings_manage": "Change store settings",
    "seller_applications.review": "Approve or reject seller applications",
    "stores.suspend": "Suspend stores",
    # Users and support
    "users.read": "View user accounts",
    "users.read_ticket": "View users linked to an assigned support ticket",
    "users.block": "Block and unblock users",
    "reviews.hide": "Hide reviews",
    "support.tickets_handle": "Answer and resolve support tickets",
    "support.tickets_assign": "Assign and escalate support tickets",
    "support.tickets_read": "Read all support tickets",
    # Platform and operations
    "ops.read": "View monitoring, logs and background jobs (no personal data)",
    "ops.jobs_retry": "Restart background jobs",
    "audit.read": "Read the full audit log",
    "audit.read_finance": "Read the financial part of the audit log",
    "rbac.manage": "Change roles and permissions",
    "platform.settings_manage": "Change platform settings",
}

Scope = Literal["platform", "store"]


@dataclass(frozen=True)
class RoleDef:
    code: str
    scope: Scope
    description: str
    permissions: frozenset[str]


def _role(code: str, scope: Scope, description: str, *permissions: str) -> RoleDef:
    return RoleDef(code, scope, description, frozenset(permissions))


CUSTOMER = "customer"

ROLES: tuple[RoleDef, ...] = (
    _role(CUSTOMER, "platform", "Buyer; granted on registration"),
    _role(
        "seller_owner",
        "store",
        "Store owner",
        "products.write",
        "products.delete",
        "inventory.write",
        "orders.seller_manage",
        "returns.decide",
        "refunds.initiate",
        "payments.read",
        "store.analytics_read",
        "store.finance_read",
        "store.staff_manage",
        "store.settings_manage",
    ),
    _role(
        "seller_manager",
        "store",
        "Manages products and orders; no finance or staff",
        "products.write",
        "inventory.write",
        "orders.seller_manage",
        "returns.decide",
        "store.analytics_read",
    ),
    _role(
        "seller_staff",
        "store",
        "Processes orders and stock",
        "inventory.write",
        "orders.seller_manage",
    ),
    _role(
        "support_agent",
        "platform",
        "Handles assigned tickets",
        "orders.read_ticket",
        "users.read_ticket",
        "support.tickets_handle",
    ),
    _role(
        "support_lead",
        "platform",
        "Support agent + assignment, escalation, refund initiation",
        "orders.read",
        "orders.status_override",
        "returns.decide",
        "refunds.initiate",
        "payments.read",
        "users.read",
        "reviews.hide",
        "support.tickets_handle",
        "support.tickets_assign",
    ),
    _role(
        "finance",
        "platform",
        "Transactions, refunds, reconciliation",
        "orders.read",
        "refunds.initiate",
        "refunds.approve",
        "payments.read",
        "store.finance_read",
        "audit.read_finance",
    ),
    _role(
        "developer",
        "platform",
        "Monitoring and background jobs, without personal data",
        "ops.read",
        "ops.jobs_retry",
    ),
    _role(
        "admin",
        "platform",
        "Manages users, stores, catalog and settings",
        "products.write",
        "products.delete",
        "products.moderate",
        "catalog.manage",
        "orders.read",
        "orders.status_override",
        "returns.decide",
        "payments.read",
        "store.analytics_read",
        "store.finance_read",
        "store.staff_manage",
        "seller_applications.review",
        "stores.suspend",
        "users.read",
        "users.block",
        "reviews.hide",
        "support.tickets_read",
        "ops.read",
        "audit.read",
        "platform.settings_manage",
    ),
    _role(
        "super_admin",
        "platform",
        "Everything, including roles and permissions",
        *PERMISSIONS,
    ),
)

ROLES_BY_CODE: dict[str, RoleDef] = {r.code: r for r in ROLES}

_unknown = {p for r in ROLES for p in r.permissions} - PERMISSIONS.keys()
if _unknown:
    raise RuntimeError(f"roles reference unknown permissions: {sorted(_unknown)}")
