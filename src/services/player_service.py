"""Player-related service functions."""
import re
from src.rcon_client import run_command, get_online_players
from src.database import get_db


def get_player_stats(player, user_id):
    """Get player statistics like health, food, XP, etc."""
    stats = {}
    
    # Get Health
    result = run_command(f"/data get entity {player} Health", user_id)
    if not str(result).startswith("Error"):
        match = re.search(r'(\d+\.?\d*)f?', str(result))
        if match:
            stats["health"] = float(match.group(1))
    
    # Get Food Level
    result = run_command(f"/data get entity {player} foodLevel", user_id)
    if not str(result).startswith("Error"):
        match = re.search(r'(\d+)', str(result))
        if match:
            stats["food"] = int(match.group(1))
    
    # Get XP Level
    result = run_command(f"/data get entity {player} XpLevel", user_id)
    if not str(result).startswith("Error"):
        match = re.search(r'(\d+)', str(result))
        if match:
            stats["xp_level"] = int(match.group(1))
    
    # Get Game Mode
    result = run_command(f"/data get entity {player} playerGameType", user_id)
    if not str(result).startswith("Error"):
        match = re.search(r'(\d+)', str(result))
        if match:
            game_modes = {0: "Survival", 1: "Creative", 2: "Adventure", 3: "Spectator"}
            stats["game_mode"] = game_modes.get(int(match.group(1)), "Unknown")
    
    return stats


def get_player_inventory(player, user_id):
    """Get player inventory items (simplified version using recent items)."""
    db = get_db()
    recent_items = db.execute(
        "SELECT item, used_count, last_used FROM item_usage WHERE user_id = ? ORDER BY last_used DESC LIMIT 20",
        [user_id]
    ).fetchall()
    
    inventory = [{
        "item": row["item"],
        "count": row["used_count"],
        "last_used": row["last_used"]
    } for row in recent_items]
    
    return inventory


def get_player_history(player, user_id):
    """Get recent actions for a player from item usage history."""
    db = get_db()
    history = db.execute(
        "SELECT item, used_count, last_used FROM item_usage WHERE user_id = ? ORDER BY last_used DESC LIMIT 15",
        [user_id]
    ).fetchall()
    
    actions = [{
        "action": f"Received {row['item']}",
        "count": row["used_count"],
        "timestamp": row["last_used"]
    } for row in history]
    
    return actions


def get_player_location(player, user_id):
    """Get player's current coordinates."""
    result = run_command(f"/data get entity {player} Pos", user_id)
    if str(result).startswith("Error"):
        return None, result

    match = re.search(r"\[(.*?)\]", str(result))
    if not match:
        return None, "Could not parse position"

    try:
        parts = [p.strip().rstrip('d') for p in match.group(1).split(',')]
        x, y, z = (int(float(p)) for p in parts[:3])
        return {"x": x, "y": y, "z": z}, None
    except Exception:
        return None, "Could not parse position"
