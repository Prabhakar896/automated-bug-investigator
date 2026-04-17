"""
Tests for user_service — all tests pass (clean module).
"""

import pytest
from src.services.user_service import (
    create_user,
    deactivate_user,
    get_user,
    list_users,
    reset_store,
)


@pytest.fixture(autouse=True)
def clean_store():
    """Reset user store before each test."""
    reset_store()
    yield
    reset_store()


class TestCreateUser:
    def test_create_valid_user(self):
        user = create_user("Alice Smith", "alice@example.com")
        assert user.name == "Alice Smith"
        assert user.email == "alice@example.com"
        assert user.is_active is True

    def test_create_user_trims_whitespace(self):
        user = create_user("  Bob  ", "  Bob@Test.com  ")
        assert user.name == "Bob"
        assert user.email == "bob@test.com"

    def test_create_user_empty_name_raises(self):
        with pytest.raises(ValueError, match="name cannot be empty"):
            create_user("", "test@example.com")

    def test_create_user_invalid_email_raises(self):
        with pytest.raises(ValueError, match="Invalid email"):
            create_user("Test", "not-an-email")

    def test_create_user_duplicate_email_raises(self):
        create_user("User1", "dup@example.com")
        with pytest.raises(ValueError, match="already registered"):
            create_user("User2", "dup@example.com")


class TestGetUser:
    def test_get_existing_user(self):
        user = create_user("Test", "test@example.com")
        found = get_user(user.id)
        assert found is not None
        assert found.id == user.id

    def test_get_nonexistent_user_returns_none(self):
        assert get_user("nonexistent-id") is None


class TestListUsers:
    def test_list_empty(self):
        assert list_users() == []

    def test_list_active_only(self):
        u1 = create_user("Active", "active@example.com")
        u2 = create_user("Inactive", "inactive@example.com")
        deactivate_user(u2.id)
        users = list_users()
        assert len(users) == 1
        assert users[0].id == u1.id


class TestDeactivateUser:
    def test_deactivate_existing(self):
        user = create_user("Test", "test@example.com")
        assert deactivate_user(user.id) is True
        assert get_user(user.id).is_active is False

    def test_deactivate_nonexistent(self):
        assert deactivate_user("fake-id") is False
