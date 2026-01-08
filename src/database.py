"""Database connection and initialization module."""
import os
import sqlite3
from flask import g
from werkzeug.security import generate_password_hash

# Allow overriding DB path via env so container volume mounts can control location
DB_PATH = os.environ.get("DB_PATH", "/app/data/data.db")


def get_db():
    """Get database connection from Flask's g object."""
    db = getattr(g, "_db", None)
    if db is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        db = sqlite3.connect(DB_PATH, check_same_thread=False)
        db.row_factory = sqlite3.Row
        g._db = db
    return db


def close_db(exception):
    """Close database connection."""
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


def init_db():
    """Initialize database tables."""
    db = get_db()

    # RCON configuration table (single row)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS rcon_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            host TEXT,
            port INTEGER,
            password TEXT
        )
        """
    )
    
    # Create locations table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS locations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            icon TEXT DEFAULT 'map-marker-alt',
            description TEXT,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            z INTEGER NOT NULL
        )
        """
    )
    
    # Create item usage table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS item_usage (
            item TEXT PRIMARY KEY,
            used_count INTEGER NOT NULL DEFAULT 0,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # Create error logs table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS error_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            command_type TEXT NOT NULL,
            command TEXT NOT NULL,
            error_message TEXT NOT NULL,
            player TEXT,
            endpoint TEXT
        )
        """
    )
    
    # Create users table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
        """
    )
    
    # Check if any user exists (to create initial admin)
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count == 0:
        admin_username = os.environ.get("ADMIN_USERNAME", "admin")
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin")
        print(f"Creating initial admin user: {admin_username}")
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (admin_username, generate_password_hash(admin_password), 'admin')
        )
    
    db.commit()
