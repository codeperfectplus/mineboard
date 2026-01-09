"""Location management service."""
from typing import Optional
from src.database import get_db
from src.config_loader import load_json_config


def seed_locations_if_empty(user_id: Optional[int] = None):
    """Seed locations from config for a user if database is empty for that user."""
    if user_id is None:
        return
        
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM locations WHERE user_id = ?", (user_id,)).fetchone()[0]
    if count == 0:
        seed = load_json_config('locations.json').get('locations', [])
        for loc in seed:
            coords = loc.get('coordinates', {})
            db.execute(
                "INSERT OR REPLACE INTO locations (id, user_id, name, icon, description, x, y, z) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    loc.get('id'),
                    user_id,
                    loc.get('name'),
                    loc.get('icon', 'map-marker-alt'),
                    loc.get('description', ''),
                    int(coords.get('x', 0)),
                    int(coords.get('y', 0)),
                    int(coords.get('z', 0)),
                ),
            )
        db.commit()


def fetch_locations(user_id: Optional[int] = None):
    """Get all locations from database for a specific user."""
    if user_id is None:
        return []
        
    db = get_db()
    rows = db.execute(
        "SELECT id, name, icon, description, x, y, z FROM locations WHERE user_id = ? ORDER BY name",
        (user_id,)
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "icon": row["icon"],
            "description": row["description"],
            "coordinates": {"x": row["x"], "y": row["y"], "z": row["z"]},
        }
        for row in rows
    ]


def upsert_location(user_id: int, data):
    """Create or update a location for a specific user."""
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO locations (id, user_id, name, icon, description, x, y, z) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            data["id"],
            user_id,
            data["name"],
            data.get("icon", "map-marker-alt"),
            data.get("description", ""),
            int(data["x"]),
            int(data["y"]),
            int(data["z"]),
        ),
    )
    db.commit()


def delete_location(user_id: int, loc_id):
    """Delete a location by ID for a specific user."""
    db = get_db()
    db.execute("DELETE FROM locations WHERE id = ? AND user_id = ?", (loc_id, user_id))
    db.commit()
