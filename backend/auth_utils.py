# backend/auth_utils.py
import bcrypt

def hash_password(password: str) -> str:
    """Hash a plain password string."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plain password against the stored hash."""
    return bcrypt.checkpw(password.encode(), stored_hash.encode())
