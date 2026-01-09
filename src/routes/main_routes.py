"""Main application routes."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from src.rcon_client import get_online_players
from src.services.item_service import build_item_catalog
from src.services.location_service import fetch_locations
from src.commands import VILLAGE_TYPES
from src.config_loader import get_kits, get_quick_commands
from src.services.config_service import get_rcon_config, save_rcon_config
from src.rcon_client import reset_rcon_client

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def dashboard():
    """Main dashboard page."""
    user_id = current_user.id
    players = get_online_players(user_id)
    kits_config = get_kits()
    quick_commands = get_quick_commands()
    
    return render_template(
        "dashboard.html",
        players=players,
        items=build_item_catalog(user_id),
        village_types=VILLAGE_TYPES,
        locations=fetch_locations(user_id),
        kits=kits_config.get("kits", []),
        quick_commands=quick_commands if isinstance(quick_commands, list) else [],
    )


@main_bp.route('/settings')
@login_required
def settings():
    """RCON settings page."""
    rcon_config = get_rcon_config(current_user.id)
    return render_template("settings.html", rcon_config=rcon_config)


@main_bp.route('/rcon-config', methods=['POST'])
@login_required
def update_rcon_config():
    """Allow users to save RCON settings."""
    user_id = current_user.id

    host = (request.form.get('host') or '').strip()
    port_raw = (request.form.get('port') or '').strip()
    password = (request.form.get('password') or '').strip()

    errors = []
    if not host:
        errors.append("Host is required")
    if not port_raw:
        errors.append("Port is required")
    try:
        port_val = int(port_raw)
    except ValueError:
        errors.append("Port must be a number")
        port_val = None
    if not password:
        errors.append("Password is required")

    if errors:
        for err in errors:
            flash(err)
        return redirect(url_for('main.settings'))

    save_rcon_config(user_id, host, port_val, password)
    reset_rcon_client(user_id)
    flash("RCON settings saved. New connections will use these values.")
    return redirect(url_for('main.settings', test_connection='true'))


@main_bp.route('/error-logs')
@login_required
def error_logs_page():
    """Dedicated error logs page."""
    return render_template("error_logs.html")


@main_bp.route('/player')
@login_required
def player():
    """Player management page."""
    players = get_online_players(current_user.id)
    return render_template("player.html", players=players)
