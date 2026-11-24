import argparse
import asyncio
from collections.abc import Sequence
import getpass
import os
import sys

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from ecommerce.core.db.sessions import engine, session_factory
from ecommerce.core.exceptions.base import ConflictError
from ecommerce.core.exceptions.db import map_integrity_error
from ecommerce.core.redis import redis_client
from ecommerce.modules.auth.models import Role, User
from ecommerce.modules.auth.schemas import RegisterRequest
from ecommerce.modules.auth.service import AuthService
from ecommerce.uow import AppUnitOfWork


async def create_admin(uow: AppUnitOfWork, email: str, password: str) -> User:
    # register never touches Redis, and the client connects lazily.
    service = AuthService(uow, redis_client)
    try:
        return await service.register(
            RegisterRequest(email=email, password=password), Role.ADMIN
        )
    except IntegrityError as exc:
        raise map_integrity_error(exc) from exc


async def _create_and_dispose(email: str, password: str) -> None:
    try:
        await create_admin(AppUnitOfWork(session_factory), email, password)
    finally:
        await engine.dispose()


def _read_password() -> str:
    password = os.environ.get("ADMIN_PASSWORD")
    if password is not None:
        return password
    password = getpass.getpass("Password: ")
    if getpass.getpass("Repeat password: ") != password:
        raise ValueError("Passwords do not match")
    return password


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ecommerce.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "create-admin", help="create a user with the admin role"
    ).add_argument("email")
    args = parser.parse_args(argv)

    try:
        password = _read_password()
        # Validate up front so bad input exits 2 before any connection is opened.
        RegisterRequest(email=args.email, password=password)
    except ValidationError as exc:
        # Never format the exception itself: it echoes input_value, i.e. the password.
        reasons = "; ".join(
            f"{err['loc'][-1]}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        sys.stderr.write(f"Invalid input: {reasons}\n")
        return 2
    except ValueError as exc:
        sys.stderr.write(f"Invalid input: {exc}\n")
        return 2
    try:
        asyncio.run(_create_and_dispose(args.email, password))
    except ConflictError as exc:
        sys.stderr.write(f"{exc.detail}\n")
        return 1
    sys.stdout.write(f"Admin {args.email.lower()} created\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
