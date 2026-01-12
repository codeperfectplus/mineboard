"""Mineboard - Flask application for Minecraft Server Control."""
import os
from flask import Flask
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix
from src.database import get_db, close_db, init_db
from src.services.location_service import seed_locations_if_empty
from src.models import User

# Create Flask app with assets served from /static
app = Flask(__name__, 
            template_folder="src/templates",
            static_folder="src/assets", 
            static_url_path="/static")
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# Configure proxy handling
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Check for URL prefix in environment variables
url_prefix = os.environ.get("URL_PREFIX")
if url_prefix:
    class PrefixMiddleware:
        def __init__(self, app, prefix=''):
            self.app = app
            self.prefix = prefix

        def __call__(self, environ, start_response):
            if environ['PATH_INFO'].startswith(self.prefix):
                environ['PATH_INFO'] = environ['PATH_INFO'][len(self.prefix):]
                environ['SCRIPT_NAME'] = self.prefix
                return self.app(environ, start_response)
            else:
                environ['SCRIPT_NAME'] = self.prefix
                return self.app(environ, start_response)
    
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=url_prefix)

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
from src.routes.chat_routes import chat_bp

app.register_blueprint(main_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(api_bp)
app.register_blueprint(command_bp)
app.register_blueprint(chat_bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5090, debug=True)
