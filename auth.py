"""
Google API Authentication Module
Uses environment variables for OAuth 2.0 credentials.
"""
import os
import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes required for Drive and Photos access
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
PHOTOS_SCOPES = [
    'https://www.googleapis.com/auth/photoslibrary.appendonly',
    'https://www.googleapis.com/auth/photoslibrary.sharing'  # Required for album creation
]

TOKEN_DIR = Path(__file__).parent


def get_credentials_config():
    """Build OAuth credentials config from environment variables."""
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')

    if not client_id or not client_secret:
        raise ValueError(
            "Missing required environment variables: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET\n"
            "Set these from your Google Cloud Console OAuth 2.0 credentials."
        )

    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]
        }
    }


def authenticate(scopes: list, token_file: str) -> Credentials:
    """
    Authenticate with Google API using OAuth 2.0.

    Args:
        scopes: List of API scopes to request
        token_file: Name of the token pickle file to save/load credentials

    Returns:
        Authenticated credentials object
    """
    token_path = TOKEN_DIR / token_file
    creds = None

    # Load existing token if available
    if token_path.exists():
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    # Refresh or get new credentials if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            config = get_credentials_config()
            flow = InstalledAppFlow.from_client_config(config, scopes)
            creds = flow.run_local_server(port=0)

        # Save credentials for future use
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    return creds


def get_drive_service():
    """Get authenticated Google Drive service."""
    creds = authenticate(DRIVE_SCOPES, 'token_drive.pickle')
    return build('drive', 'v3', credentials=creds)


def get_photos_credentials():
    """Get authenticated credentials for Google Photos API."""
    return authenticate(PHOTOS_SCOPES, 'token_photos.pickle')
