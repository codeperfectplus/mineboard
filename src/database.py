"""Database connection and initialization module."""
import os
import sqlite3
from flask import g
from werkzeug.security import generate_password_hash

# Determine data directory based on working directory
# If running from /opt/mineboard, use /opt/mineboard/data
# Otherwise use /app/data for Docker compatibility
if os.getcwd().startswith('/opt/mineboard'):
    DEFAULT_DB_PATH = "/opt/mineboard/data/data.db"
if os.getcwd().startswith('/app'):
    DEFAULT_DB_PATH = "/app/data/data.db"
else:
    DEFAULT_DB_PATH = "./data/data.db"

# Allow overriding DB path via env so container volume mounts can control location
DB_PATH = os.environ.get("DB_PATH", DEFAULT_DB_PATH)


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

    # RCON configuration table (per-user)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS rcon_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            host TEXT,
            port INTEGER,
            password TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id)
        )
        """
    )
    
    # Create locations table (per-user)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS locations (
            id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            icon TEXT DEFAULT 'map-marker-alt',
            description TEXT,
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            z INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY (id, user_id)
        )
        """
    )
    
    # Create item usage table (per-user)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS item_usage (
            item TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            used_count INTEGER NOT NULL DEFAULT 0,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY (item, user_id)
        )
        """
    )
    
    # Create error logs table (per-user)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS error_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            command_type TEXT NOT NULL,
            command TEXT NOT NULL,
            error_message TEXT NOT NULL,
            player TEXT,
            endpoint TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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
            role TEXT DEFAULT 'user',
            first_name TEXT,
            last_name TEXT,
            gamer_tag TEXT
        )
        """
    )

    # Check for missing columns in users table (migration for existing dbs)
    try:
        db.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
    except sqlite3.OperationalError:
        pass # Column likely exists
    try:
        db.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE users ADD COLUMN gamer_tag TEXT")
    except sqlite3.OperationalError:
        pass
    
    # Create messages table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            recipient_id INTEGER, -- Null if group chat
            group_id INTEGER, -- Null if 1-on-1 chat
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            read BOOLEAN DEFAULT 0,
            FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE
        )
        """
    )
    
    # Create chat groups table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        )
        """
    )
    
    # Create group members table
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS group_members (
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES chat_groups(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY (group_id, user_id)
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
            "INSERT INTO users (username, password_hash, role, first_name, last_name, gamer_tag) VALUES (?, ?, ?, ?, ?, ?)",
            (admin_username, generate_password_hash(admin_password), 'admin', 'System', 'Admin', 'Operator')
        )
        
    # Check for missing last_read_at in group_members (migration)
    try:
        db.execute("ALTER TABLE group_members ADD COLUMN last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass
    
    db.commit()
