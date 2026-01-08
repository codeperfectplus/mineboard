"""RCON configuration helpers with env override and DB persistence."""
import os
from typing import Dict, Any
from dotenv import load_dotenv
from src.database import get_db

# Ensure .env is loaded before accessing environment variables
load_dotenv()

DEFAULT_RCON_HOST = "localhost"
DEFAULT_RCON_PORT = 25575


def _env_values():
    host = os.getenv("RCON_HOST")
    port = os.getenv("RCON_PORT")
    password = os.getenv("RCON_PASSWORD")
    return host, port, password


def env_has_rcon() -> bool:
    """Return True when all RCON env vars are present."""
    host, port, password = _env_values()
    return bool(host) and bool(port) and bool(password)


def get_rcon_config() -> Dict[str, Any]:
    """Return effective RCON config, preferring environment variables over DB."""
    host_env, port_env, password_env = _env_values()
    if env_has_rcon():
        try:
            port_val = int(port_env)
        except (TypeError, ValueError):
            port_val = DEFAULT_RCON_PORT
        return {
            "host": host_env,
            "port": port_val,
            "password": password_env or "",
            "source": "env",
        }

    db = get_db()
    row = db.execute("SELECT host, port, password FROM rcon_config WHERE id = 1").fetchone()
    if row:
        port_val = row["port"] if row["port"] is not None else DEFAULT_RCON_PORT
        return {
            "host": row["host"] or DEFAULT_RCON_HOST,
            "port": int(port_val),
            "password": row["password"] or "",
            "source": "db",
        }

    return {
        "host": DEFAULT_RCON_HOST,
        "port": DEFAULT_RCON_PORT,
        "password": "",
        "source": "default",
    }


def save_rcon_config(host: str, port: int, password: str) -> None:
    """Persist RCON config into the database (id=1)."""
    db = get_db()
    db.execute(
        """
        INSERT INTO rcon_config (id, host, port, password)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            host = excluded.host,
            port = excluded.port,
            password = excluded.password
        """,
        (host, port, password),
    )
    db.commit()


def rcon_config_source_label(config: Dict[str, Any]) -> str:
    """Human-friendly label for template use."""
    source = config.get("source")
    if source == "env":
        return "Environment (.env)"
    if source == "db":
        return "Saved in app (DB)"
    return "Defaults"
