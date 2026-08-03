import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parents[2]


def test_compose_source_interpolates_the_jwt_secret() -> None:
    """A production secret must be supplied by the environment, never committed."""
    source = yaml.safe_load((ROOT / "compose.yaml").read_text())

    assert source["services"]["api"]["environment"]["JWT_SECRET"] == "${JWT_SECRET}"


def test_rendered_compose_has_healthy_postgres_and_migrating_api() -> None:
    """Render Compose before asserting the runtime topology that Docker will use."""
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker compose is unavailable: docker executable was not found")

    compose_version = subprocess.run(
        [docker, "compose", "version"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if compose_version.returncode != 0:
        pytest.skip("docker compose is unavailable: Compose plugin was not found")

    environment = {
        **os.environ,
        "DATABASE_URL": "postgresql+asyncpg://shop:shop@db:5432/shop",
        "POSTGRES_DB": "shop",
        "POSTGRES_USER": "shop",
        "POSTGRES_PASSWORD": "compose-test-password",
        "JWT_SECRET": "compose-test-jwt-secret",
        "ACCESS_TOKEN_MINUTES": "30",
    }
    result = subprocess.run(
        [docker, "compose", "config"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    config = yaml.safe_load(result.stdout)

    assert set(config["services"]) == {"api", "db"}
    assert config["services"]["db"]["image"] == "postgres:16"
    assert "healthcheck" in config["services"]["db"]
    assert "pg_isready" in config["services"]["db"]["healthcheck"]["test"]
    assert config["services"]["api"]["depends_on"]["db"]["condition"] == "service_healthy"

    api_environment = config["services"]["api"]["environment"]
    assert {"DATABASE_URL", "JWT_SECRET", "ACCESS_TOKEN_MINUTES"} <= set(api_environment)
    assert api_environment["JWT_SECRET"] == environment["JWT_SECRET"]

    command = config["services"]["api"]["command"]
    assert command.index("alembic upgrade head") < command.index("uvicorn app.main:app")
