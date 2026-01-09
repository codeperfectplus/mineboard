"""Error logging service."""
from typing import Optional
from src.database import get_db


def log_error(user_id: int, command_type, command, error_message, player=None, endpoint=None):
    """Log command errors to database for debugging and monitoring."""
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO error_logs (user_id, command_type, command, error_message, player, endpoint)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, command_type, command, error_message, player, endpoint),
        )
        db.commit()
        print(f"[ERROR_LOG] User {user_id} - {command_type}: {error_message}")
    except Exception as e:
        print(f"Failed to log error: {e}")


def get_error_logs(user_id: Optional[int] = None, limit=50):
    """Retrieve recent error logs for a specific user or all users (admin)."""
    db = get_db()
    if user_id is not None:
        rows = db.execute(
            """
            SELECT id, timestamp, command_type, command, error_message, player, endpoint
            FROM error_logs
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (user_id, limit)
        ).fetchall()
    else:
        # Admin view - all logs
        rows = db.execute(
            """
            SELECT id, timestamp, command_type, command, error_message, player, endpoint, user_id
            FROM error_logs
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
    
    return [
        {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "command_type": row["command_type"],
            "command": row["command"],
            "error_message": row["error_message"],
            "player": row["player"],
            "endpoint": row["endpoint"],
            "user_id": row.get("user_id") if user_id is None else None,
        }
        for row in rows
    ]


def clear_error_logs(user_id: Optional[int] = None):
    """Clear error logs for a specific user or all users (admin)."""
    db = get_db()
    if user_id is not None:
        db.execute("DELETE FROM error_logs WHERE user_id = ?", (user_id,))
    else:
        db.execute("DELETE FROM error_logs")
    db.commit()
