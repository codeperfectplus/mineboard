"""RCON configuration helpers with database persistence."""
import os
from typing import Dict, Any, Optional
from src.database import get_db

DEFAULT_RCON_HOST = "localhost"
DEFAULT_RCON_PORT = 25575


def get_rcon_config(user_id: Optional[int] = None) -> Dict[str, Any]:
    """Return RCON config for a user from database.
    
    Args:
        user_id: User ID to get config for. If None, returns defaults.
    """
    if user_id is None:
        return {
            "host": DEFAULT_RCON_HOST,
            "port": DEFAULT_RCON_PORT,
            "password": "",
            "source": "default",
            "user_id": None,
        }

    db = get_db()
    row = db.execute(
        "SELECT host, port, password FROM rcon_config WHERE user_id = ?", 
        (user_id,)
    ).fetchone()
    
    if row:
        port_val = row["port"] if row["port"] is not None else DEFAULT_RCON_PORT
        return {
            "host": row["host"] or DEFAULT_RCON_HOST,
            "port": int(port_val),
            "password": row["password"] or "",
            "source": "db",
            "user_id": user_id,
        }

    return {
        "host": DEFAULT_RCON_HOST,
        "port": DEFAULT_RCON_PORT,
        "password": "",
        "source": "default",
        "user_id": user_id,
    }


def save_rcon_config(user_id: int, host: str, port: int, password: str) -> None:
    """Persist RCON config into the database for a specific user."""
    db = get_db()
    db.execute(
        """
        INSERT INTO rcon_config (user_id, host, port, password)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            host = excluded.host,
            port = excluded.port,
            password = excluded.password
        """,
        (user_id, host, port, password),
    )
    db.commit()


def rcon_config_source_label(config: Dict[str, Any]) -> str:
    """Human-friendly label for template use."""
    source = config.get("source")
    if source == "db":
        return "Saved in Database"
    return "Not Configured"
