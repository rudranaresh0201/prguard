import os
from github import Github, GithubException
from backend.config import GROQ_MODEL

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")

def get_github_client():
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN not set")
    return Github(GITHUB_TOKEN)

def get_repo():
    g = get_github_client()
    return g.get_repo(GITHUB_REPO)

def get_pr_diff(pr_number: int) -> str:
    """Get the full diff for a PR."""
    import httpx
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3.diff"
    }
    repo = GITHUB_REPO
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    response = httpx.get(url, headers=headers)
    return response.text

def post_pr_comment(pr_number: int, body: str) -> dict:
    """Post a comment on a PR."""
    repo = get_repo()
    pr = repo.get_pull(pr_number)
    comment = pr.create_issue_comment(body)
    return {"comment_id": comment.id, "url": comment.html_url}

def post_review_comment(pr_number: int, body: str, commit_sha: str, path: str, line: int) -> dict:
    """Post an inline review comment on a specific line."""
    repo = get_repo()
    pr = repo.get_pull(pr_number)
    commit = repo.get_commit(commit_sha)
    comment = pr.create_review_comment(body=body, commit=commit, path=path, line=line)
    return {"comment_id": comment.id, "url": comment.html_url}

def add_pr_label(pr_number: int, label: str) -> None:
    """Add a label to a PR."""
    repo = get_repo()
    pr = repo.get_pull(pr_number)
    pr.add_to_labels(label)

def merge_pr(pr_number: int, commit_message: str = "Merged by Governance Agent") -> dict:
    """Merge a PR."""
    repo = get_repo()
    pr = repo.get_pull(pr_number)
    result = pr.merge(commit_message=commit_message)
    return {"merged": result.merged, "sha": result.sha, "message": result.message}

def get_pr_details(pr_number: int) -> dict:
    """Get full PR details."""
    repo = get_repo()
    pr = repo.get_pull(pr_number)
    return {
        "number": pr.number,
        "title": pr.title,
        "body": pr.body or "",
        "author": pr.user.login,
        "base_branch": pr.base.ref,
        "head_branch": pr.head.ref,
        "head_sha": pr.head.sha,
        "files": [f.filename for f in pr.get_files()],
        "state": pr.state,
    }
