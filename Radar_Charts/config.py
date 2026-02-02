"""
Application configuration management.
"""
import os
import json
from google.oauth2 import service_account


class Config:
    """Central configuration for the application."""

    # Admin settings
    ADMIN_EMAIL = "tariq.khasawneh@devoteam.com"

    # Google Drive settings
    #DRIVE_FILE_ID = "1PpMb1EcjN_YUj3dtWDY5_oJphov6Q1Dc"
    DRIVE_FILE_ID = "16JpSAnF6i0n0xNpO1jREGzxPueZHitgT"
    # Google Cloud Storage settings
    BUCKET_NAME = "new-radar-chart-users3"
    USERS_FILE_NAME = "users.json"

    # Data refresh interval (seconds)
    CHECK_INTERVAL = 10

    # Gemini settings
    GEMINI_MODEL = "gemini-1.5-flash"

    @staticmethod
    def get_credentials():
        """Get Google service account credentials from environment."""
        service_account_json = os.getenv("SERVICE_ACCOUNT")
        if not service_account_json:
            raise Exception("Missing SERVICE_ACCOUNT environment variable")
        credentials_dict = json.loads(service_account_json)
        return service_account.Credentials.from_service_account_info(credentials_dict)

    @staticmethod
    def get_gemini_api_key():
        """Get Gemini API key from environment."""
        return os.getenv("GEMINI_API_KEY")
