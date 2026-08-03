import asyncio
import os

import pytest
from alembic.config import Config
from sqlalchemy import pool, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from typer.testing import CliRunner

from alembic import command
from app import cli
from app.core.security import verify_password
from app.users.models import Role, User


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", os.environ["TEST_DATABASE_URL"])
    return config


def _users_with_email(email: str) -> list[User]:
    async def read_users() -> list[User]:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"], poolclass=pool.NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                result = await session.execute(select(User).where(User.email == email))
                return list(result.scalars())
        finally:
            await engine.dispose()

    return asyncio.run(read_users())


def test_create_or_promote_creates_one_normalized_active_admin_without_echoing_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Would fail if the command duplicates users, skips promotion, or exposes the password."""
    config = _alembic_config()
    engine = None

    try:
        command.downgrade(config, "base")
        command.upgrade(config, "head")
        runner = CliRunner()
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"], poolclass=pool.NullPool)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(cli, "async_session_factory", session_factory)
        created = runner.invoke(
            cli.app,
            [
                "create-or-promote",
                "--email",
                "Admin@Example.com",
                "--password",
                "first secure password",
            ],
        )
        promoted = runner.invoke(
            cli.app,
            ["create-or-promote", "--email", "Admin@Example.com"],
            input="replacement secure password\n",
        )

        assert created.exit_code == 0, created.output
        assert promoted.exit_code == 0, promoted.output
        assert created.output == "admin@example.com: created\n"
        assert promoted.output == "Password: \nadmin@example.com: promoted\n"
        assert "replacement secure password" not in promoted.output

        users = _users_with_email("admin@example.com")
        assert len(users) == 1
        assert users[0].role is Role.ADMIN
        assert users[0].is_active is True
        assert verify_password("replacement secure password", users[0].password_hash)
    finally:
        if engine is not None:
            asyncio.run(engine.dispose())
        command.upgrade(config, "head")
