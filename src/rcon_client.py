from mcrcon import MCRcon
import socket
import signal
import threading
from typing import Optional
from src.services.config_service import get_rcon_config

# Monkey-patch signal.signal to avoid threading issues
original_signal = signal.signal
def safe_signal(signalnum, handler):
    """Only allow signal handling in main thread"""
    if threading.current_thread() is threading.main_thread():
        return original_signal(signalnum, handler)
    return None

signal.signal = safe_signal

# Per-user connection pool
_client_pool = {}
_pool_lock = threading.Lock()


def _connect_new(user_id: Optional[int] = None):
    """Create and connect a new RCON client for a specific user."""
    cfg = get_rcon_config(user_id)
    client = MCRcon(cfg["host"], cfg["password"], port=cfg["port"], timeout=3)
    try:
        client.connect()
        return client
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        # Fail fast - don't block the application
        raise ConnectionError(f"Failed to connect to RCON server at {cfg['host']}:{cfg['port']}") from e


def _get_client(user_id: Optional[int] = None):
    """Return a connected RCON client for the user (thread-safe)."""
    global _client_pool
    cache_key = user_id if user_id is not None else "default"
    
    with _pool_lock:
        if cache_key not in _client_pool or _client_pool[cache_key] is None:
            _client_pool[cache_key] = _connect_new(user_id)
        return _client_pool[cache_key]


def run_command(command: str, user_id: Optional[int] = None):
    """Execute a command on the Minecraft server via RCON with connection reuse.
    
    Args:
        command: The RCON command to execute
        user_id: User ID to use their specific server connection
    """
    try:
        client = _get_client(user_id)
        return client.command(command)
    except ConnectionError:
        return "Error: Cannot connect to RCON server. Please configure RCON settings in the Settings page."
    except (socket.timeout, ConnectionRefusedError, OSError) as conn_err:
        cache_key = user_id if user_id is not None else "default"
        with _pool_lock:
            _client_pool[cache_key] = None
        if isinstance(conn_err, socket.timeout):
            return "Error: Connection timed out. Is the Minecraft server running?"
        return "Error: Connection refused. Make sure Minecraft server is running and RCON is enabled."
    except Exception as e:
        error_msg = str(e)
        if "Authentication failed" in error_msg or "Login failed" in error_msg:
            cache_key = user_id if user_id is not None else "default"
            with _pool_lock:
                _client_pool[cache_key] = None
            return "Error: Authentication failed. Check RCON password in settings."

        # Attempt one reconnect+retry on a broken pipe/socket closure
        try:
            cache_key = user_id if user_id is not None else "default"
            with _pool_lock:
                try:
                    if cache_key in _client_pool and _client_pool[cache_key]:
                        _client_pool[cache_key].disconnect()
                except Exception:
                    pass
                _client_pool[cache_key] = _connect_new(user_id)
                return _client_pool[cache_key].command(command)
        except (ConnectionError, socket.timeout, ConnectionRefusedError, OSError):
            with _pool_lock:
                _client_pool[cache_key] = None
            return "Error: Cannot connect to RCON server. Please check your settings."
        except Exception:
            return f"Error: {error_msg}"


def reset_rcon_client(user_id: Optional[int] = None):
    """Drop the cached client for a user so new config is picked up on next command."""
    global _client_pool
    cache_key = user_id if user_id is not None else "default"
    
    with _pool_lock:
        try:
            if cache_key in _client_pool and _client_pool[cache_key]:
                _client_pool[cache_key].disconnect()
        except Exception:
            pass
        _client_pool[cache_key] = None

def is_rcon_error(response):
    """Check if RCON response indicates an error."""
    if not response:
        return False
    error_indicators = [
        "Error:",
        "Unknown command",
        "No player was found",
        "Unable to modify",
        "Invalid",
        "Incorrect argument",
        "Expected",
        "Cannot",
        "Failed",
    ]
    return any(indicator in response for indicator in error_indicators)


def parse_rcon_response(response):
    """Parse RCON response and return structured result.
    
    Returns:
        dict with 'success', 'message', and 'data' keys
    """
    if not response or response.strip() == "":
        return {"success": True, "message": "Command executed", "data": None}
    
    if is_rcon_error(response):
        return {"success": False, "message": response, "data": None}
    
    return {"success": True, "message": response, "data": response}


def get_online_players(user_id: Optional[int] = None):
    """Get list of online players for a specific user's server"""
    try:
        response = run_command("list", user_id)
        # Parse response like "There are 2 of a max of 20 players online: player1, player2"
        if "Error" in response or not response:
            # Return empty list silently - don't block UI
            return []
        if "online:" in response:
            players_str = response.split("online:")[1].strip()
            if players_str:
                return [p.strip() for p in players_str.split(",")]
        return []
    except Exception as e:
        # Fail gracefully - don't block the application
        return []
