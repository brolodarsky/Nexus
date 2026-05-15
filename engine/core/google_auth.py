import os
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

def get_google_credentials(scopes: list[str], secrets_dir: str) -> Credentials:
    """
    Generic Google OAuth2 credential handler.
    Loads existing tokens, refreshes them if expired, or triggers a browser-based login flow.
    
    Args:
        scopes: List of OAuth2 scopes required.
        secrets_dir: Path to the directory containing 'credentials.json' and where 'token.json' will be saved.
        
    Returns:
        A valid google.oauth2.credentials.Credentials object.
    """
    token_file = os.path.join(secrets_dir, "token.json")
    credentials_file = os.path.join(secrets_dir, "credentials.json")
    
    creds = None
    
    # 1. Look for pre-existing local tokens
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, scopes)
        
    # 2. If token is missing or expired, resolve it
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                # If refresh fails (e.g. revoked), we need to re-auth
                print(f"Token refresh failed: {e}. Re-authenticating...")
                creds = None
        
        if not creds:
            # Requires credentials.json from Google Console
            if not os.path.exists(credentials_file):
                print(
                    f"Error: '{credentials_file}' not found.\n"
                    " Please download your Desktop Client OAuth credentials from Google Cloud Console\n"
                    f" and save them in {secrets_dir} to authorize your account.",
                    file=sys.stderr
                )
                sys.exit(1)
            
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, scopes)
            creds = flow.run_local_server(port=0)
            
            # Save structural tokens for subsequent headless calls
            os.makedirs(secrets_dir, exist_ok=True)
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
            
    return creds
