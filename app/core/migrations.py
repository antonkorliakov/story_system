import os

from alembic.config import Config


def configure_database_url(alembic_config: Config) -> str:
    """Apply an explicit runtime database URL without replacing caller configuration."""
    configured_url = alembic_config.get_main_option("sqlalchemy.url")
    if configured_url is None:
        raise RuntimeError("Alembic requires sqlalchemy.url")

    if _is_programmatic_override(alembic_config, configured_url):
        return configured_url

    database_url = os.environ.get("DATABASE_URL")
    if database_url is None:
        return configured_url

    alembic_config.set_main_option("sqlalchemy.url", database_url)
    return database_url


def _is_programmatic_override(alembic_config: Config, configured_url: str) -> bool:
    config_file_name = alembic_config.config_file_name
    if config_file_name is None:
        return True
    file_config = Config(config_file_name, ini_section=alembic_config.config_ini_section)
    return configured_url != file_config.get_main_option("sqlalchemy.url")
