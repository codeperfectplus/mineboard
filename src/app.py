from flask import Flask, render_template, request, redirect, url_for, jsonify, g, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from src.rcon_client import run_command, get_online_players
from src.commands import ITEMS, VILLAGE_TYPES
from collections import OrderedDict
import re
import json
import os
import sqlite3

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role
    
    @staticmethod
    def get(user_id):
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if not user:
            return None
        return User(id=user['id'], username=user['username'], role=user['role'])

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

# Allow overriding DB path via env so container volume mounts can control location
DB_PATH = os.environ.get("DB_PATH", "/app/data/data.db")

# Quick lookup for item metadata
ITEM_INDEX = {
    item["name"]: {**item, "category": category}
    for category, items in ITEMS.items()
    for item in items
}


def get_db():
    db = getattr(g, "_db", None)
    if db is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        db = sqlite3.connect(DB_PATH, check_same_thread=False)
        db.row_factory = sqlite3.Row
        g._db = db
    return db


@app.teardown_appcontext
def close_db(exception):
    db = getattr(g, "_db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
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
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS item_usage (
            item TEXT PRIMARY KEY,
            used_count INTEGER NOT NULL DEFAULT 0,
            last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
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


def load_json_config(filename):
    config_path = os.path.join(os.path.dirname(__file__), 'config', filename)
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: Config file not found: {config_path}")
        return {}
    except json.JSONDecodeError:
        print(f"Error: Could not parse JSON config file: {config_path}")
        return {}


def seed_locations_if_empty():
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    if count == 0:
        seed = load_json_config('locations.json').get('locations', [])
        for loc in seed:
            coords = loc.get('coordinates', {})
            db.execute(
                "INSERT OR REPLACE INTO locations (id, name, icon, description, x, y, z) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    loc.get('id'),
                    loc.get('name'),
                    loc.get('icon', 'map-marker-alt'),
                    loc.get('description', ''),
                    int(coords.get('x', 0)),
                    int(coords.get('y', 0)),
                    int(coords.get('z', 0)),
                ),
            )
        db.commit()


def fetch_locations():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, icon, description, x, y, z FROM locations ORDER BY name"
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


def record_item_usage(item_name, amount=1):
    """Persist item usage counts for quick-access ordering."""
    if item_name not in ITEM_INDEX:
        return
    try:
        amount_int = max(int(amount), 1)
    except (TypeError, ValueError):
        amount_int = 1

    db = get_db()
    db.execute(
        """
        INSERT INTO item_usage (item, used_count, last_used)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(item) DO UPDATE SET
            used_count = item_usage.used_count + excluded.used_count,
            last_used = CURRENT_TIMESTAMP
        """,
        (item_name, amount_int),
    )
    db.commit()


def fetch_usage_counts():
    db = get_db()
    rows = db.execute("SELECT item, used_count FROM item_usage").fetchall()
    return {row["item"]: row["used_count"] for row in rows}


def log_error(command_type, command, error_message, player=None, endpoint=None):
    """Log command errors to database for debugging and monitoring."""
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO error_logs (command_type, command, error_message, player, endpoint)
            VALUES (?, ?, ?, ?, ?)
            """,
            (command_type, command, error_message, player, endpoint),
        )
        db.commit()
        print(f"[ERROR_LOG] {command_type}: {error_message}")
    except Exception as e:
        print(f"Failed to log error: {e}")


def get_error_logs(limit=50):
    """Retrieve recent error logs."""
    db = get_db()
    rows = db.execute(
        """
        SELECT id, timestamp, command_type, command, error_message, player, endpoint
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
        }
        for row in rows
    ]


def get_top_used_items(usage_counts, limit=8):
    ranked = sorted(
        ((name, count) for name, count in usage_counts.items() if name in ITEM_INDEX),
        key=lambda pair: (-pair[1], ITEM_INDEX[pair[0]].get("display", pair[0])),
    )
    top = []
    for name, count in ranked[:limit]:
        entry = {**ITEM_INDEX[name], "used_count": count}
        top.append(entry)
    return top


def build_item_catalog():
    """Return ordered item categories with optional usage data."""
    usage_counts = fetch_usage_counts()
    catalog = OrderedDict()

    top_items = get_top_used_items(usage_counts)
    if top_items:
        catalog["Most Used"] = top_items

    for category, items in ITEMS.items():
        catalog[category] = []
        for item in items:
            entry = dict(item)
            used = usage_counts.get(item["name"])
            if used:
                entry["used_count"] = used
            catalog[category].append(entry)
    return catalog


def upsert_location(data):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO locations (id, name, icon, description, x, y, z) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            data["id"],
            data["name"],
            data.get("icon", "map-marker-alt"),
            data.get("description", ""),
            int(data["x"]),
            int(data["y"]),
            int(data["z"]),
        ),
    )
    db.commit()


def delete_location(loc_id):
    db = get_db()
    db.execute("DELETE FROM locations WHERE id = ?", (loc_id,))
    db.commit()


with app.app_context():
    init_db()
    seed_locations_if_empty()

# Load kits
KITS_CONFIG = load_json_config('kits.json')

# Load quick commands
QUICK_COMMANDS = load_json_config('quick_commands.json')
print(f"Loaded {len(QUICK_COMMANDS) if isinstance(QUICK_COMMANDS, list) else 0} quick commands.")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user_data = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(id=user_data['id'], username=user_data['username'], role=user_data['role'])
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/admin/users', methods=['GET', 'POST'])
@login_required
def manage_users():
    if current_user.role != 'admin':
        flash('Access denied: Admin only')
        return redirect(url_for('dashboard'))
    
    db = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            username = request.form['username']
            password = request.form['password']
            role = request.form.get('role', 'user')
            
            try:
                db.execute(
                    "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    (username, generate_password_hash(password), role)
                )
                db.commit()
                flash(f'User {username} created successfully')
            except sqlite3.IntegrityError:
                flash(f'Username {username} already exists')
        elif action == 'delete':
             user_id = request.form['user_id']
             if int(user_id) == current_user.id:
                 flash('Cannot delete yourself')
             else:
                 db.execute("DELETE FROM users WHERE id = ?", (user_id,))
                 db.commit()
                 flash('User deleted')
            
    users = db.execute("SELECT id, username, role FROM users").fetchall()
    return render_template('manage_users.html', users=users)

@app.route("/")
@login_required
def dashboard():
    players = get_online_players()
    return render_template(
        "dashboard.html",
        players=players,
        items=build_item_catalog(),
        village_types=VILLAGE_TYPES,
        locations=fetch_locations(),
        kits=KITS_CONFIG.get("kits", []),
        quick_commands=QUICK_COMMANDS if isinstance(QUICK_COMMANDS, list) else [],
    )

@app.route("/diagnostics")
@login_required
def diagnostics():
    """RCON diagnostics page"""
    return render_template("diagnostics.html")


@app.route("/api/error-logs")
@login_required
def api_error_logs():
    """API endpoint to retrieve error logs"""
    limit = request.args.get('limit', 50, type=int)
    logs = get_error_logs(limit)
    return jsonify({"success": True, "logs": logs})


@app.route("/error-logs")
@login_required
def error_logs_page():
    """Dedicated error logs page"""
    return render_template("error_logs.html")


@app.route("/api/error-logs/clear", methods=["POST"])
@login_required
def clear_error_logs():
    """Clear all error logs"""
    try:
        db = get_db()
        db.execute("DELETE FROM error_logs")
        db.commit()
        return jsonify({"success": True, "message": "All error logs cleared"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/player")
@login_required
def player():
    """Player management page"""
    players = get_online_players()
    return render_template("player.html", players=players)

@app.route("/api/players")
@login_required
def api_players():
    """API endpoint to refresh player list"""
    players = get_online_players()
    return jsonify({"players": players, "count": len(players)})

@app.route("/api/test-connection")
@login_required
def test_connection():
    """Test RCON connection and return diagnostics"""
    from rcon_client import RCON_HOST, RCON_PORT, RCON_PASSWORD
    
    result = run_command("list")
    
    diagnostics = {
        "host": RCON_HOST,
        "port": RCON_PORT,
        "password_set": bool(RCON_PASSWORD and RCON_PASSWORD.strip()),
        "password_length": len(RCON_PASSWORD) if RCON_PASSWORD else 0,
        "response": result,
        "connected": not result.startswith("Error")
    }
    
    return jsonify(diagnostics)


@app.route("/api/locations", methods=["GET", "POST"])
@login_required
def api_locations():
    if request.method == "GET":
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


@app.route("/api/locations/<loc_id>", methods=["PUT", "PATCH", "DELETE"])
@login_required
def api_location_detail(loc_id):
    if request.method == "DELETE":
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


@app.route("/api/player-stats", methods=["POST"])
@login_required
def api_player_stats():
    """Get player statistics like health, food, XP, etc."""
    player = request.form.get("player") if request.form else (request.json or {}).get("player")
    if not player:
        return jsonify({"success": False, "error": "Player is required"}), 400

    stats = {}
    
    # Get Health
    result = run_command(f"/data get entity {player} Health")
    if not str(result).startswith("Error"):
        match = re.search(r'(\d+\.?\d*)f?', str(result))
        if match:
            stats["health"] = float(match.group(1))
    
    # Get Food Level
    result = run_command(f"/data get entity {player} foodLevel")
    if not str(result).startswith("Error"):
        match = re.search(r'(\d+)', str(result))
        if match:
            stats["food"] = int(match.group(1))
    
    # Get XP Level
    result = run_command(f"/data get entity {player} XpLevel")
    if not str(result).startswith("Error"):
        match = re.search(r'(\d+)', str(result))
        if match:
            stats["xp_level"] = int(match.group(1))
    
    # Get Game Mode
    result = run_command(f"/data get entity {player} playerGameType")
    if not str(result).startswith("Error"):
        match = re.search(r'(\d+)', str(result))
        if match:
            game_modes = {0: "Survival", 1: "Creative", 2: "Adventure", 3: "Spectator"}
            stats["game_mode"] = game_modes.get(int(match.group(1)), "Unknown")
    
    return jsonify({"success": True, "stats": stats})


@app.route("/api/player-inventory", methods=["POST"])
@login_required
def api_player_inventory():
    """Get player inventory items (simplified version)"""
    player = request.form.get("player") if request.form else (request.json or {}).get("player")
    if not player:
        return jsonify({"success": False, "error": "Player is required"}), 400
    
    # This is a simplified version. Full inventory parsing would require complex NBT data parsing
    # For now, we'll return item usage history as "recent items"
    db = get_db()
    recent_items = db.execute(
        "SELECT item, used_count, last_used FROM item_usage ORDER BY last_used DESC LIMIT 20"
    ).fetchall()
    
    inventory = [{
        "item": row["item"],
        "count": row["used_count"],
        "last_used": row["last_used"]
    } for row in recent_items]
    
    return jsonify({"success": True, "inventory": inventory})


@app.route("/api/player-history", methods=["POST"])
@login_required
def api_player_history():
    """Get recent actions for a player from item usage history"""
    player = request.form.get("player") if request.form else (request.json or {}).get("player")
    if not player:
        return jsonify({"success": False, "error": "Player is required"}), 400
    
    # Get recent item usage as history
    db = get_db()
    history = db.execute(
        "SELECT item, used_count, last_used FROM item_usage ORDER BY last_used DESC LIMIT 15"
    ).fetchall()
    
    actions = [{
        "action": f"Received {row['item']}",
        "count": row["used_count"],
        "timestamp": row["last_used"]
    } for row in history]
    
    return jsonify({"success": True, "history": actions})


@app.route("/api/player-location", methods=["POST"])
@login_required
def api_player_location():
    player = request.form.get("player") if request.form else (request.json or {}).get("player")
    if not player:
        return jsonify({"success": False, "error": "Player is required"}), 400

    result = run_command(f"/data get entity {player} Pos")
    if str(result).startswith("Error"):
        return jsonify({"success": False, "error": result}), 400

    match = re.search(r"\[(.*?)\]", str(result))
    if not match:
        return jsonify({"success": False, "error": "Could not parse position"}), 400

    try:
        parts = [p.strip().rstrip('d') for p in match.group(1).split(',')]
        x, y, z = (int(float(p)) for p in parts[:3])
    except Exception:
        return jsonify({"success": False, "error": "Could not parse position"}), 400

    return jsonify({"success": True, "coordinates": {"x": x, "y": y, "z": z}})

@app.route("/command", methods=["POST"])
@login_required
def execute_command():
    """Execute any Minecraft command"""
    cmd = request.form.get("command")
    player = request.form.get("player")
    
    if player and "@p" in cmd:
        cmd = cmd.replace("@p", player)
    elif player and not any(x in cmd for x in ["@p", "@a", "@s"]):
        # If command doesn't have a selector, try to add player name
        if cmd.startswith("/"):
            cmd = f"{cmd} {player}"
    
    result = run_command(cmd)
    return jsonify({"success": True, "result": result})

@app.route("/tp", methods=["POST"])
@login_required
def teleport():
    print("\n=== TELEPORT REQUEST ===")
    player = request.form.get("player")
    location_id = request.form.get("location_id")
    print(f"Player: {player}")
    print(f"Location ID: {location_id}")
    
    location = next((loc for loc in fetch_locations() if loc['id'] == location_id), None)
    
    if location:
        coords = location['coordinates']
        cmd = f"/tp {player} {coords['x']} {coords['y']} {coords['z']}"
        print(f"Executing command: {cmd}")
        result = run_command(cmd)
        print(f"RCON result: {result}")
        
        # Log teleport errors
        from rcon_client import is_rcon_error
        if is_rcon_error(result):
            log_error(
                command_type="teleport",
                command=cmd,
                error_message=result,
                player=player,
                endpoint="/tp"
            )
        
        return jsonify({"success": True, "result": result})
    else:
        print(f"ERROR: Location not found: {location_id}")
        log_error(
            command_type="teleport",
            command="N/A",
            error_message=f"Location not found: {location_id}",
            player=player,
            endpoint="/tp"
        )
        return jsonify({"success": False, "error": "Location not found"})


@app.route("/tp/coordinates", methods=["POST"])
@login_required
def teleport_coordinates():
    print("\n=== TELEPORT COORD REQUEST ===")
    player = request.form.get("player")
    try:
        x = int(request.form.get("x"))
        y = int(request.form.get("y"))
        z = int(request.form.get("z"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Coordinates must be numbers"}), 400

    if not player:
        return jsonify({"success": False, "error": "Player is required"}), 400

    cmd = f"/tp {player} {x} {y} {z}"
    print(f"Executing coord teleport: {cmd}")
    result = run_command(cmd)
    print(f"RCON result: {result}")
    return jsonify({"success": True, "result": result})


@app.route("/api/usage/<item_name>", methods=["DELETE"])
@login_required
def delete_item_usage(item_name):
    db = get_db()
    db.execute("DELETE FROM item_usage WHERE item = ?", (item_name,))
    db.commit()
    return jsonify({"success": True})


@app.route("/give", methods=["POST"])
@login_required
def give_item():
    print("\n=== GIVE ITEM REQUEST ===")
    player = request.form.get("player")
    item = request.form.get("item")
    amount_raw = request.form.get("amount", 1)
    try:
        amount = max(1, min(64, int(amount_raw)))
    except (TypeError, ValueError):
        amount = 1
    print(f"Player: {player}")
    print(f"Item: {item}")
    print(f"Amount: {amount}")
    cmd = f"/give {player} minecraft:{item} {amount}"
    print(f"Executing command: {cmd}")
    result = run_command(cmd)
    print(f"RCON result: {result}")
    
    # Log errors and only record usage if successful
    from rcon_client import is_rcon_error
    if is_rcon_error(result):
        log_error(
            command_type="give_item",
            command=cmd,
            error_message=result,
            player=player,
            endpoint="/give"
        )
    else:
        record_item_usage(item, amount)
    
    return jsonify({"success": True, "result": result})

@app.route("/locate", methods=["POST"])
@login_required
def locate_village():
    player = request.form["player"]
    village_type = request.form["village_type"]
    cmd = f"/execute as {player} run locate structure minecraft:village_{village_type}"
    result = run_command(cmd)
    
    # Log locate errors
    from rcon_client import is_rcon_error
    if is_rcon_error(result):
        log_error(
            command_type="locate_village",
            command=cmd,
            error_message=result,
            player=player,
            endpoint="/locate"
        )
    
    return jsonify({"success": True, "result": result})

@app.route("/quick-command", methods=["POST"])
@login_required
def quick_command():
    """Execute quick gameplay commands"""
    print("\n=== QUICK COMMAND REQUEST ===")
    player = request.form.get("player")
    command_type = request.form.get("command_type")
    print(f"Player: {player}")
    print(f"Command Type: {command_type}")
    
    commands_map = {
        # Gamemode
        "gamemode_survival": f"/gamemode survival {player}",
        "gamemode_creative": f"/gamemode creative {player}",
        "gamemode_adventure": f"/gamemode adventure {player}",
        
        # Player Actions
        "heal": f"/effect give {player} minecraft:instant_health 1 10",
        "feed": f"/effect give {player} minecraft:saturation 1 10",
        "clear_inventory": f"/clear {player}",
        "give_xp": f"/xp add {player} 1000",
        
        # Effects
        "speed": f"/effect give {player} minecraft:speed 600 2",
        "jump_boost": f"/effect give {player} minecraft:jump_boost 600 2",
        "night_vision": f"/effect give {player} minecraft:night_vision 600 0",
        "water_breathing": f"/effect give {player} minecraft:water_breathing 600 0",
        "fire_resistance": f"/effect give {player} minecraft:fire_resistance 600 0",
        "clear_effects": f"/effect clear {player}",
        
        # World Control
        "day": "/time set day",
        "night": "/time set night",
        "clear_weather": "/weather clear",
        "rain": "/weather rain",
        "thunder": "/weather thunder",
        "save_world": "/save-all",
        
        # Time Control
        "time_dawn": "/time set 0",
        "time_noon": "/time set 6000",
        "time_dusk": "/time set 12000",
        "time_midnight": "/time set 18000",
        
        # Difficulty
        "difficulty_peaceful": "/difficulty peaceful",
        "difficulty_normal": "/difficulty normal",
        "difficulty_hard": "/difficulty hard",
        
        # Game Rules
        "keep_inventory_on": "/gamerule keepInventory true",
        "keep_inventory_off": "/gamerule keepInventory false",
        "mob_griefing_off": "/gamerule mobGriefing false",
        "mob_griefing_on": "/gamerule mobGriefing true",
        "daylight_cycle_off": "/gamerule doDaylightCycle false",
        "daylight_cycle_on": "/gamerule doDaylightCycle true",
        
        # World Border
        "worldborder_small": "/worldborder set 500 30",
        "worldborder_medium": "/worldborder set 2000 60",
        "worldborder_large": "/worldborder set 5000 120",
        "worldborder_infinite": "/worldborder set 60000000 0",
        
        # Admin & Utility
        "op_player": f"/op {player}",
        "deop_player": f"/deop {player}",
        "whitelist_add": f"/whitelist add {player}",
        "whitelist_remove": f"/whitelist remove {player}",
        "xp_reset": f"/xp set {player} 0 points",
        "hero_of_village": f"/effect give {player} minecraft:hero_of_the_village 1200 0",
        
        # Village Helpers
        "spawn_villager_farmer": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:farmer\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_librarian": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:librarian\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_cleric": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:cleric\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_armorer": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:armorer\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_weaponsmith": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:weaponsmith\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_toolsmith": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:toolsmith\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_butcher": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:butcher\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_cartographer": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:cartographer\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_fisherman": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:fisherman\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_fletcher": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:fletcher\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_shepherd": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:shepherd\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_leatherworker": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:leatherworker\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_mason": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:mason\",type:\"minecraft:plains\",level:5}}",
        "spawn_villager_nitwit": "/summon villager ~ ~ ~ {VillagerData:{profession:\"minecraft:nitwit\",type:\"minecraft:plains\",level:5}}",
        "spawn_iron_golem": "/summon iron_golem ~ ~ ~",
        "spawn_cat": "/summon cat ~ ~ ~ {CatType:0}",
        
        # Mob Control
        "kill_hostile_mobs": "/kill @e[type=!player,type=!item,type=!villager,type=!iron_golem,type=!horse,type=!cat,type=!wolf,type=!parrot,type=!donkey,type=!mule,type=!llama,type=!trader_llama]",
        "kill_passive_mobs": "/kill @e[type=cow] /kill @e[type=sheep] /kill @e[type=pig] /kill @e[type=chicken]",
        "kill_all_entities": "/kill @e[type=!player]",
        "kill_item_entities": "/kill @e[type=item]",
        "clear_ground_items": "/kill @e[type=item]",
        
        # Advanced Player
        "full_restore": f"/effect give {player} minecraft:instant_health 1 10",
        "fly_mode": f"/effect give {player} minecraft:levitation 1000000 255 true",
        "fly_enable": f"/effect give {player} minecraft:levitation 1000000 255 true",
        "fly_disable": f"/effect clear {player} minecraft:levitation",
        "godmode_on": f"/effect give {player} minecraft:resistance 1000000 255 true",
        "max_health": f"/attribute {player} minecraft:generic.max_health base set 1024",
        "full_health": f"/effect give {player} minecraft:regeneration 10 255",
    }
    
    cmd = commands_map.get(command_type)
    if cmd:
        print(f"Executing command: {cmd}")
        result = run_command(cmd)
        print(f"RCON result: {result}")
        
        # Parse the RCON response to determine success
        from rcon_client import is_rcon_error
        
        # Check for RCON errors
        if is_rcon_error(result):
            print(f"Command failed: {result}")
            # Log the error
            log_error(
                command_type=command_type,
                command=cmd,
                error_message=result,
                player=player,
                endpoint="/quick-command"
            )
            return jsonify({
                "success": False, 
                "error": result,
                "command": cmd
            })
        
        return jsonify({
            "success": True, 
            "result": result,
            "message": result if result else "Command executed successfully"
        })
    
    print(f"ERROR: Unknown command type: {command_type}")
    # Log unknown command type
    log_error(
        command_type=command_type,
        command="N/A",
        error_message=f"Unknown command type: {command_type}",
        player=player,
        endpoint="/quick-command"
    )
    return jsonify({"success": False, "error": f"Unknown command type: {command_type}"})

@app.route("/kit/<kit_id>", methods=["POST"])
def give_kit(kit_id):
    print("\n=== GIVE KIT REQUEST ===")
    player = request.form.get("player")
    print(f"Player: {player}")
    print(f"Kit ID: {kit_id}")
    
    # Find kit in config
    kits = KITS_CONFIG.get('kits', [])
    kit = next((k for k in kits if k['id'] == kit_id), None)
    
    if kit:
        print(f"Found kit: {kit['name']}")
        results = []
        for item_data in kit['items']:
            cmd = f"/give {player} minecraft:{item_data['item']} {item_data['amount']}"
            print(f"Executing: {cmd}")
            result = run_command(cmd)
            print(f"Result: {result}")
            results.append(result)
            
            # Log errors from kit commands
            from rcon_client import is_rcon_error
            if is_rcon_error(result):
                log_error(
                    command_type=f"kit_{kit_id}",
                    command=cmd,
                    error_message=result,
                    player=player,
                    endpoint="/kit"
                )
            if not str(result).startswith("Error"):
                record_item_usage(item_data["item"], item_data["amount"])
        return jsonify({"success": True, "results": results})
    
    print(f"ERROR: Kit not found: {kit_id}")
    return jsonify({"success": False, "error": "Kit not found"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5090, debug=True)
