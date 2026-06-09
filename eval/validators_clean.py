import re
import os
import bcrypt
from typing import Optional

SECRET_KEY = os.getenv("SECRET_KEY")

def validate_email(email: str) -> bool:
    """Validate email format.

    Args:
        email: Email string to validate
    Returns:
        True if valid, False otherwise
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def hash_password(password: str) -> str:
    """Hash password using bcrypt.

    Args:
        password: Plain text password
    Returns:
        Hashed password
    """
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()

def get_user_safe(db, user_id: int) -> Optional[dict]:
    """Fetch user safely.

    Args:
        db: Database connection
        user_id: User ID
    Returns:
        User or None
    """
    if not isinstance(user_id, int) or user_id <= 0:
        return None
    return db.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
