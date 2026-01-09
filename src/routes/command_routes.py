"""Command execution routes."""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from src.rcon_client import run_command, is_rcon_error
from src.services.item_service import record_item_usage
from src.services.location_service import fetch_locations
from src.services.error_service import log_error
from src.commands import VILLAGE_TYPES
from src.config_loader import get_kits

command_bp = Blueprint('command', __name__)


@command_bp.route('/command', methods=['POST'])
@login_required
def execute_command():
    """Execute any Minecraft command."""
    cmd = request.form.get("command")
    player = request.form.get("player")
    
    if player and "@p" in cmd:
        cmd = cmd.replace("@p", player)
    elif player and not any(x in cmd for x in ["@p", "@a", "@s"]):
        # If command doesn't have a selector, try to add player name
        if cmd.startswith("/"):
            cmd = f"{cmd} {player}"
    
    result = run_command(cmd, current_user.id)
    return jsonify({"success": True, "result": result})


@command_bp.route('/tp', methods=['POST'])
@login_required
def teleport():
    """Teleport player to a saved location."""
    print("\n=== TELEPORT REQUEST ===")
    player = request.form.get("player")
    location_id = request.form.get("location_id")
    print(f"Player: {player}")
    print(f"Location ID: {location_id}")
    
    location = next((loc for loc in fetch_locations(current_user.id) if loc['id'] == location_id), None)
    
    if location:
        coords = location['coordinates']
        cmd = f"/tp {player} {coords['x']} {coords['y']} {coords['z']}"
        print(f"Executing command: {cmd}")
        result = run_command(cmd, current_user.id)
        print(f"RCON result: {result}")
        
        if is_rcon_error(result):
            log_error(
                current_user.id,
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
            current_user.id,
            command_type="teleport",
            command="N/A",
            error_message=f"Location not found: {location_id}",
            player=player,
            endpoint="/tp"
        )
        return jsonify({"success": False, "error": "Location not found"})


@command_bp.route('/tp/coordinates', methods=['POST'])
@login_required
def teleport_coordinates():
    """Teleport player to specific coordinates."""
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
    result = run_command(cmd, current_user.id)
    print(f"RCON result: {result}")
    return jsonify({"success": True, "result": result})


@command_bp.route('/give', methods=['POST'])
@login_required
def give_item():
    """Give an item to a player."""
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
    result = run_command(cmd, current_user.id)
    print(f"RCON result: {result}")
    
    if is_rcon_error(result):
        log_error(
            current_user.id,
            command_type="give_item",
            command=cmd,
            error_message=result,
            player=player,
            endpoint="/give"
        )
    else:
        record_item_usage(current_user.id, item, amount)
    
    return jsonify({"success": True, "result": result})


@command_bp.route('/locate', methods=['POST'])
@login_required
def locate_village():
    """Locate a village type."""
    player = request.form["player"]
    village_type = request.form["village_type"]
    cmd = f"/execute as {player} run locate structure minecraft:village_{village_type}"
    result = run_command(cmd, current_user.id)
    
    if is_rcon_error(result):
        log_error(
            current_user.id,
            command_type="locate_village",
            command=cmd,
            error_message=result,
            player=player,
            endpoint="/locate"
        )
    
    return jsonify({"success": True, "result": result})


@command_bp.route('/quick-command', methods=['POST'])
@login_required
def quick_command():
    """Execute quick gameplay commands."""
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
        result = run_command(cmd, current_user.id)
        print(f"RCON result: {result}")
        
        if is_rcon_error(result):
            print(f"Command failed: {result}")
            log_error(
                current_user.id,
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
    log_error(
        current_user.id,
        command_type=command_type,
        command="N/A",
        error_message=f"Unknown command type: {command_type}",
        player=player,
        endpoint="/quick-command"
    )
    return jsonify({"success": False, "error": f"Unknown command type: {command_type}"})


@command_bp.route('/kit/<kit_id>', methods=['POST'])
@login_required
def give_kit(kit_id):
    """Give a kit to a player."""
    print("\n=== GIVE KIT REQUEST ===")
    player = request.form.get("player")
    print(f"Player: {player}")
    print(f"Kit ID: {kit_id}")
    
    kits_config = get_kits()
    kits = kits_config.get('kits', [])
    kit = next((k for k in kits if k['id'] == kit_id), None)
    
    if kit:
        print(f"Found kit: {kit['name']}")
        results = []
        for item_data in kit['items']:
            cmd = f"/give {player} minecraft:{item_data['item']} {item_data['amount']}"
            print(f"Executing: {cmd}")
            result = run_command(cmd, current_user.id)
            print(f"Result: {result}")
            results.append(result)
            
            if is_rcon_error(result):
                log_error(
                    current_user.id,
                    command_type=f"kit_{kit_id}",
                    command=cmd,
                    error_message=result,
                    player=player,
                    endpoint="/kit"
                )
            if not str(result).startswith("Error"):
                record_item_usage(current_user.id, item_data["item"], item_data["amount"])
        return jsonify({"success": True, "results": results})
    
    print(f"ERROR: Kit not found: {kit_id}")
    return jsonify({"success": False, "error": "Kit not found"})
