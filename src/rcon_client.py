from mcrcon import MCRcon
import os
import socket
import signal
import threading
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

RCON_HOST = os.getenv("RCON_HOST", "localhost")
RCON_PORT = int(os.getenv("RCON_PORT", "25575"))
RCON_PASSWORD = os.getenv("RCON_PASSWORD", "")

# Monkey-patch signal.signal to avoid threading issues
original_signal = signal.signal
def safe_signal(signalnum, handler):
    """Only allow signal handling in main thread"""
    if threading.current_thread() is threading.main_thread():
        return original_signal(signalnum, handler)
    return None

signal.signal = safe_signal

_client = None
_client_lock = threading.Lock()


def _connect_new():
    """Create and connect a new RCON client."""
    client = MCRcon(RCON_HOST, RCON_PASSWORD, port=RCON_PORT)
    client.connect()
    return client


def _get_client():
    """Return a connected, shared RCON client (thread-safe)."""
    global _client
    with _client_lock:
        if _client is None:
            _client = _connect_new()
        return _client


def run_command(command):
    """Execute a command on the Minecraft server via RCON with connection reuse."""
    try:
        client = _get_client()
        return client.command(command)
    except (socket.timeout, ConnectionRefusedError) as conn_err:
        return "Error: Connection timed out. Is the Minecraft server running?" if isinstance(conn_err, socket.timeout) else "Error: Connection refused. Make sure Minecraft server is running and RCON is enabled."
    except Exception as e:
        error_msg = str(e)
        if "Authentication failed" in error_msg or "Login failed" in error_msg:
            return "Error: Authentication failed. Check RCON password in .env file."

        # Attempt one reconnect+retry on a broken pipe/socket closure
        try:
            with _client_lock:
                try:
                    if _client:
                        _client.disconnect()
                except Exception:
                    pass
                _client = _connect_new()
                return _client.command(command)
        except Exception:
            return f"Error: {error_msg}"

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


def get_online_players():
    """Get list of online players"""
    try:
        response = run_command("list")
        # Parse response like "There are 2 of a max of 20 players online: player1, player2"
        if "Error" in response:
            print(f"RCON Error: {response}")
            return []
        if "online:" in response:
            players_str = response.split("online:")[1].strip()
            if players_str:
                return [p.strip() for p in players_str.split(",")]
        return []
    except Exception as e:
        print(f"Exception getting players: {e}")
        return []
