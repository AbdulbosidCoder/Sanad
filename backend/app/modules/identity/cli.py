"""Developer commands for the `identity` module.

    python -m app.modules.identity.cli sync-rbac
    python -m app.modules.identity.cli grant-role <email-or-phone> <role>

``grant-role`` is how the first admin is created: register through the API, then
grant ``super_admin`` from the server shell. Platform roles only.
"""

import argparse
import asyncio
import sys

from app.core.db import get_sessionmaker
from app.core.errors import AppError
from app.modules.identity import service
from app.modules.identity.rbac import ROLES


async def _sync() -> None:
    async with get_sessionmaker()() as db:
        await service.sync_rbac(db)
        await db.commit()
    print(f"synced {len(ROLES)} roles")


async def _grant(login: str, role: str) -> int:
    async with get_sessionmaker()() as db:
        await service.sync_rbac(db)
        user_id = await service.find_user_id(db, login)
        if user_id is None:
            print(f"user not found: {login}", file=sys.stderr)
            return 1
        try:
            await service.grant_role(db, user_id, role)
        except AppError as exc:
            print(exc.detail, file=sys.stderr)
            return 1
    print(f"granted {role} to {login}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.modules.identity.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync-rbac", help="write roles and permissions from rbac.py")
    grant = sub.add_parser("grant-role", help="give a platform role to a user")
    grant.add_argument("login", help="email or phone")
    grant.add_argument("role", choices=[r.code for r in ROLES if r.scope == "platform"])
    args = parser.parse_args(argv)

    if args.command == "sync-rbac":
        asyncio.run(_sync())
        return 0
    return asyncio.run(_grant(args.login, args.role))


if __name__ == "__main__":
    raise SystemExit(main())
