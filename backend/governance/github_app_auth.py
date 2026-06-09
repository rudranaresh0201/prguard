import time
import os
import requests
import jwt

GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_APP_PRIVATE_KEY = os.getenv("GITHUB_APP_PRIVATE_KEY")

def generate_jwt() -> str:
    """Generate a JWT for GitHub App authentication."""
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + (9 * 60),
        "iss": GITHUB_APP_ID,
    }
    private_key = GITHUB_APP_PRIVATE_KEY.replace("\\n", "\n")
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token

def get_installation_token(installation_id: int) -> str:
    """Exchange installation_id for a repo-scoped access token."""
    app_jwt = generate_jwt()
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.post(url, headers=headers)
    response.raise_for_status()
    return response.json()["token"]

def get_github_client_for_installation(installation_id: int):
    """Get a PyGitHub client scoped to a specific installation."""
    from github import Github
    token = get_installation_token(installation_id)
    return Github(token)
