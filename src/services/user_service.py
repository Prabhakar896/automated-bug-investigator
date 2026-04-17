"""
User service — handles user CRUD operations.
This module is clean (no bugs) and acts as noise for the investigation agents.
"""

import logging
from typing import Dict, Optional

from src.models import User
from src.utils import validate_email

logger = logging.getLogger("app.user_service")

# In-memory user store
_users: Dict[str, User] = {}


def create_user(name: str, email: str) -> User:
    """Create a new user after validation."""
    if not name or not name.strip():
        raise ValueError("User name cannot be empty")
    
    if not validate_email(email):
        raise ValueError(f"Invalid email format: {email}")
    
    # Check for duplicate email
    for user in _users.values():
        if user.email == email:
            raise ValueError(f"Email already registered: {email}")
    
    user = User(name=name.strip(), email=email.lower().strip())
    _users[user.id] = user
    logger.info(f"Created user {user.id}: {user.name} ({user.email})")
    return user


def get_user(user_id: str) -> Optional[User]:
    """Retrieve a user by ID."""
    return _users.get(user_id)


def list_users() -> list:
    """List all active users."""
    return [u for u in _users.values() if u.is_active]


def deactivate_user(user_id: str) -> bool:
    """Soft-delete a user by marking them inactive."""
    user = _users.get(user_id)
    if user is None:
        return False
    user.is_active = False
    logger.info(f"Deactivated user {user_id}")
    return True


def reset_store():
    """Reset the in-memory store (for testing)."""
    _users.clear()
