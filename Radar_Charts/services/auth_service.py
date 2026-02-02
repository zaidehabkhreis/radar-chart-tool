"""
Authentication service for user management.
"""
import json
from typing import Optional
from google.cloud import storage
from ..config import Config


class AuthService:
    """Handles user authentication and management."""

    def __init__(self):
        self.storage_client = storage.Client()
        self.users_cache = self._fetch_users()

    def _fetch_users(self) -> dict:
        """Fetch users from Google Cloud Storage."""
        bucket = self.storage_client.bucket(Config.BUCKET_NAME)
        blob = bucket.blob(Config.USERS_FILE_NAME)

        if not blob.exists():
            raise Exception(f"Users file {Config.USERS_FILE_NAME} not found in bucket {Config.BUCKET_NAME}")

        users_json = blob.download_as_text()
        users_data = json.loads(users_json)
        return {u["email"]: u["password"] for u in users_data["users"]}

    def refresh_users(self):
        """Refresh the users cache from GCS."""
        self.users_cache = self._fetch_users()

    def save_users(self):
        """Save current users to GCS."""
        bucket = self.storage_client.bucket(Config.BUCKET_NAME)
        blob = bucket.blob(Config.USERS_FILE_NAME)
        users_data = {
            "users": [{"email": e, "password": p} for e, p in self.users_cache.items()]
        }
        blob.upload_from_string(json.dumps(users_data, indent=4), content_type="application/json")

    def validate_user(self, email: str, password: str) -> bool:
        """Validate user credentials."""
        return email in self.users_cache and self.users_cache[email] == password

    def get_authenticated_user(self, request) -> Optional[str]:
        """Get authenticated user from request cookies."""
        email = request.cookies.get("user_email")
        password = request.cookies.get("user_password")
        if self.validate_user(email, password):
            return email
        return None

    def add_user(self, email: str, password: str) -> bool:
        """Add a new user."""
        if email not in self.users_cache:
            self.users_cache[email] = password
            self.save_users()
            return True
        return False

    def update_user(self, email: str, password: str) -> bool:
        """Update user password."""
        if email in self.users_cache:
            self.users_cache[email] = password
            self.save_users()
            return True
        return False

    def remove_user(self, email: str) -> bool:
        """Remove a user."""
        if email in self.users_cache:
            del self.users_cache[email]
            self.save_users()
            return True
        return False

    def get_all_users(self) -> dict:
        """Get all users."""
        return self.users_cache.copy()

    def is_admin(self, email: str) -> bool:
        """Check if user is admin."""
        return email == Config.ADMIN_EMAIL
