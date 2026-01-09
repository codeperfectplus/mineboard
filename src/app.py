"""Flask application for Minecraft Server Control."""
import os
from flask import Flask
from flask_login import LoginManager
from src.database import get_db, close_db, init_db
from src.services.location_service import seed_locations_if_empty
from src.models import User

# Create Flask app with assets served from /static
app = Flask(__name__, static_folder="assets", static_url_path="/static")
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    user = User.get(user_id)
    if user:
        # Seed default locations for new users
        seed_locations_if_empty(user.id)
    return user

# Register database teardown
app.teardown_appcontext(close_db)

# Initialize database
with app.app_context():
    init_db()

# Register blueprints
from src.routes.main_routes import main_bp
from src.routes.auth_routes import auth_bp
from src.routes.api_routes import api_bp
from src.routes.command_routes import command_bp

app.register_blueprint(main_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(api_bp)
app.register_blueprint(command_bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5090, debug=True)
