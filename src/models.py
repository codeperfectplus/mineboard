"""User model for authentication."""
from flask_login import UserMixin
from src.database import get_db



class User(UserMixin):
    """User model for Flask-Login."""
    def __init__(self, id, username, role, force_password_change=False):
        self.id = id
        self.username = username
        self.role = role
        self.force_password_change = force_password_change

    @staticmethod
    def get(user_id):
        """Get user by ID."""
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
        if not user:
            return None
        # If password is 'admin', force password change
        from werkzeug.security import check_password_hash
        force_change = False
        if user['username'] == 'admin' and check_password_hash(user['password_hash'], 'admin'):
            force_change = True
        # Optionally, you can add a force_password_change column in DB for more flexibility
        return User(id=user['id'], username=user['username'], role=user['role'], force_password_change=force_change)
