"""User model for authentication."""
from flask_login import UserMixin
from src.database import get_db



class User(UserMixin):
    """User model for Flask-Login."""
    def __init__(self, id, username, role, first_name=None, last_name=None, gamer_tag=None, force_password_change=False):
        self.id = id
        self.username = username
        self.role = role
        self.first_name = first_name
        self.last_name = last_name
        self.gamer_tag = gamer_tag
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
        
        # safely get new fields if they exist (handling migration case subtly if column doesn't exist yet, though init_db should handle it)
        first_name = user['first_name'] if 'first_name' in user.keys() else None
        last_name = user['last_name'] if 'last_name' in user.keys() else None
        gamer_tag = user['gamer_tag'] if 'gamer_tag' in user.keys() else None

        return User(
            id=user['id'], 
            username=user['username'], 
            role=user['role'], 
            first_name=first_name,
            last_name=last_name,
            gamer_tag=gamer_tag,
            force_password_change=force_change
        )
