"""API routes for AJAX endpoints."""
import sys
import os
import platform
from flask import Blueprint, request, jsonify
from flask_login import login_required
from src.services.location_service import fetch_locations, upsert_location, delete_location
from src.services.item_service import delete_item_usage
from src.services.error_service import get_error_logs, clear_error_logs
from src.services.player_service import (
    get_player_stats, get_player_inventory, 
    get_player_history, get_player_location
)
from src.services.config_service import get_rcon_config
from src.rcon_client import run_command, get_online_players

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/players')
@login_required
def api_players():
    """API endpoint to refresh player list."""
    players = get_online_players()
    return jsonify({"players": players, "count": len(players)})


@api_bp.route('/test-connection')
@login_required
def test_connection():
    """Test RCON connection and return diagnostics."""
    cfg = get_rcon_config()

    result = run_command("list")
    
    diagnostics = {
        "host": cfg["host"],
        "port": cfg["port"],
        "password_set": bool(cfg["password"] and cfg["password"].strip()),
        "password_length": len(cfg["password"]) if cfg.get("password") else 0,
        "source": cfg.get("source"),
        "response": result,
        "connected": not str(result).startswith("Error")
    }
    
    return jsonify(diagnostics)


@api_bp.route('/app-info')
@login_required
def app_info():
    """Get application information."""
    db_path = os.environ.get("DB_PATH", "/app/data/data.db")
    db_size = 0
    if os.path.exists(db_path):
        db_size = os.path.getsize(db_path) / 1024  # KB
    
    info = {
        "version": "2.0.0",
        "environment": os.environ.get("ENVIRONMENT", "Docker"),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "database": "SQLite",
        "database_size_kb": round(db_size, 2),
        "platform": platform.system(),
        "framework": "Flask + Tailwind CSS"
    }
    
    return jsonify(info)


@api_bp.route('/locations', methods=['GET', 'POST'])
@login_required
def api_locations():
    """Get or create locations."""
    if request.method == 'GET':
        return jsonify({"locations": fetch_locations()})

    data = request.form or request.json or {}
    required = ["id", "name", "x", "y", "z"]
    missing = [r for r in required if not data.get(r)]
    if missing:
        return jsonify({"success": False, "error": f"Missing fields: {', '.join(missing)}"}), 400

    upsert_location({
        "id": str(data.get("id")).strip(),
        "name": data.get("name").strip(),
        "icon": (data.get("icon") or "map-marker-alt").strip(),
        "description": (data.get("description") or "").strip(),
        "x": int(data.get("x")),
        "y": int(data.get("y")),
        "z": int(data.get("z")),
    })
    return jsonify({"success": True})


@api_bp.route('/locations/<loc_id>', methods=['PUT', 'PATCH', 'DELETE'])
@login_required
def api_location_detail(loc_id):
    """Update or delete a specific location."""
    if request.method == 'DELETE':
        delete_location(loc_id)
        return jsonify({"success": True})

    data = request.form or request.json or {}
    payload = {
        "id": loc_id,
        "name": data.get("name"),
        "icon": data.get("icon"),
        "description": data.get("description"),
        "x": data.get("x"),
        "y": data.get("y"),
        "z": data.get("z"),
    }

    if not payload["name"]:
        return jsonify({"success": False, "error": "Missing name"}), 400

    upsert_location(payload)
    return jsonify({"success": True})


@api_bp.route('/player-stats', methods=['POST'])
@login_required
def api_player_stats():
    """Get player statistics like health, food, XP, etc."""
    player = request.form.get("player") if request.form else (request.json or {}).get("player")
    if not player:
        return jsonify({"success": False, "error": "Player is required"}), 400

    stats = get_player_stats(player)
    return jsonify({"success": True, "stats": stats})


@api_bp.route('/player-inventory', methods=['POST'])
@login_required
def api_player_inventory():
    """Get player inventory items (simplified version)."""
    player = request.form.get("player") if request.form else (request.json or {}).get("player")
    if not player:
        return jsonify({"success": False, "error": "Player is required"}), 400
    
    inventory = get_player_inventory(player)
    return jsonify({"success": True, "inventory": inventory})


@api_bp.route('/player-history', methods=['POST'])
@login_required
def api_player_history():
    """Get recent actions for a player from item usage history."""
    player = request.form.get("player") if request.form else (request.json or {}).get("player")
    if not player:
        return jsonify({"success": False, "error": "Player is required"}), 400
    
    actions = get_player_history(player)
    return jsonify({"success": True, "history": actions})


@api_bp.route('/player-location', methods=['POST'])
@login_required
def api_player_location():
    """Get player's current location."""
    player = request.form.get("player") if request.form else (request.json or {}).get("player")
    if not player:
        return jsonify({"success": False, "error": "Player is required"}), 400

    coordinates, error = get_player_location(player)
    if error:
        return jsonify({"success": False, "error": error}), 400

    return jsonify({"success": True, "coordinates": coordinates})


@api_bp.route('/error-logs')
@login_required
def api_error_logs():
    """API endpoint to retrieve error logs."""
    limit = request.args.get('limit', 50, type=int)
    logs = get_error_logs(limit)
    return jsonify({"success": True, "logs": logs})


@api_bp.route('/error-logs/clear', methods=['POST'])
@login_required
def api_clear_error_logs():
    """Clear all error logs."""
    try:
        clear_error_logs()
        return jsonify({"success": True, "message": "All error logs cleared"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@api_bp.route('/usage/<item_name>', methods=['DELETE'])
@login_required
def api_delete_item_usage(item_name):
    """Delete item usage record."""
    delete_item_usage(item_name)
    return jsonify({"success": True})
