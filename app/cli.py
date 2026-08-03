import asyncio

import typer
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.security import hash_password
from app.users.models import Role, User

app = typer.Typer()


@app.callback()
def main() -> None:
    """Administrator commands for the shop."""


@app.command()
def create_or_promote(
    email: str = typer.Option(..., help="Email address of the administrator."),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="Administrator password."),
) -> None:
    """Create an administrator or promote an existing account."""
    normalized_email = email.strip().lower()
    outcome = asyncio.run(_create_or_promote(normalized_email, password))
    typer.echo(f"{normalized_email}: {outcome}")


async def _create_or_promote(email: str, password: str) -> str:
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            session.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    role=Role.ADMIN,
                    is_active=True,
                )
            )
            outcome = "created"
        else:
            user.password_hash = hash_password(password)
            user.role = Role.ADMIN
            user.is_active = True
            outcome = "promoted"

        await session.commit()
        return outcome
