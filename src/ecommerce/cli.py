import asyncio
import os

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
import typer

from ecommerce.core.db.sessions import engine, session_factory
from ecommerce.core.exceptions.base import ConflictError
from ecommerce.core.exceptions.db import map_integrity_error
from ecommerce.core.redis import redis_client
from ecommerce.modules.auth.models import Role, User
from ecommerce.modules.auth.schemas import RegisterRequest
from ecommerce.modules.auth.service import AuthService
from ecommerce.uow import AppUnitOfWork

# Plain tracebacks: rich ones can print frame locals, i.e. the password.
app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)


@app.callback()
def _commands() -> None:
    """Management commands."""


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


@app.command("create-admin")
def create_admin_command(email: str) -> None:
    """Create a user with the admin role.

    The password is read from ADMIN_PASSWORD, otherwise asked for twice.
    """
    # Not a --password option: a password on the command line lands in shell
    # history and the process list.
    password = os.environ.get("ADMIN_PASSWORD")
    if password is None:
        password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    try:
        RegisterRequest(email=email, password=password)
    except ValidationError as exc:
        # Never format the exception itself: it echoes input_value, i.e. the password.
        reasons = "; ".join(
            f"{err['loc'][-1]}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        typer.echo(f"Invalid input: {reasons}", err=True)
        raise typer.Exit(2) from None
    try:
        asyncio.run(_create_and_dispose(email, password))
    except ConflictError as exc:
        typer.echo(exc.detail, err=True)
        raise typer.Exit(1) from None
    typer.echo(f"Admin {email.lower()} created")


if __name__ == "__main__":
    app()
