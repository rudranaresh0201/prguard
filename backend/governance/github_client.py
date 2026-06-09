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

def fetch_pr_diff(pr_number: int) -> str:
    """Fetch PR diff using PyGitHub pr.get_files(), capped at 100k characters."""
    repo = get_repo()
    pr = repo.get_pull(pr_number)

    parts = []
    total_len = 0
    MAX_LEN = 100_000

    for f in pr.get_files():
        if f.patch is None:  # binary files have no patch
            continue
        chunk = f"--- a/{f.filename}\n+++ b/{f.filename}\n{f.patch}"
        if total_len + len(chunk) > MAX_LEN:
            parts.append("[DIFF TRUNCATED]")
            break
        parts.append(chunk)
        total_len += len(chunk)

    return "\n".join(parts)

def post_pr_comment(pr_number: int, body: str) -> dict:
    """Post a comment on a PR."""
    repo = get_repo()
    pr = repo.get_pull(pr_number)
    comment = pr.create_issue_comment(body)
    return {"comment_id": comment.id, "url": comment.html_url}

GOVERNANCE_MARKER = "<!-- governance-bot -->"

def upsert_pr_comment(pr_number: int, body: str) -> None:
    """Post a new governance comment or edit the existing one."""
    repo = get_repo()
    issue = repo.get_issue(pr_number)
    full_body = GOVERNANCE_MARKER + "\n" + body
    for comment in issue.get_comments():
        if comment.body.startswith(GOVERNANCE_MARKER):
            comment.edit(full_body)
            return
    issue.create_comment(full_body)

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

# ── Checks API ──────────────────────────────────────────────────────────────
# Requires GITHUB_TOKEN with checks:write permission.
# Use a GitHub App installation token or a fine-grained PAT with
# Repository → Checks → Read and write access.
# Classic PATs do NOT have access to the Checks API.

def create_check_run(name: str, head_sha: str) -> int:
    """Create a check run in 'in_progress' state. Returns the check run ID."""
    from datetime import datetime, timezone
    repo = get_repo()
    check_run = repo.create_check_run(
        name=name,
        head_sha=head_sha,
        status="in_progress",
        started_at=datetime.now(timezone.utc),
    )
    return check_run.id


def complete_check_run(
    check_run_id: int,
    conclusion: str,
    title: str,
    summary: str,
    annotations: list = None,
) -> None:
    """Update a check run to 'completed'.

    conclusion: 'success' | 'failure' | 'neutral' | 'action_required'
    annotations: list of dicts — path, start_line, end_line, annotation_level, message.
                 GitHub caps annotations at 50 per update call.
    """
    from datetime import datetime, timezone
    repo = get_repo()
    check_run = repo.get_check_run(check_run_id)
    output = {"title": title, "summary": summary}
    if annotations:
        output["annotations"] = annotations[:50]
    check_run.edit(
        status="completed",
        conclusion=conclusion,
        completed_at=datetime.now(timezone.utc),
        output=output,
    )


def build_security_annotations(diff: str) -> list:
    """Scan a PR diff for security patterns; return Check API annotation dicts.

    Parses unified diff headers to map added lines back to their file positions,
    then flags lines matching known-bad patterns with file-level annotations.
    Falls back gracefully if the diff format is unexpected.
    """
    import re

    # (regex, annotation_level, title)
    PATTERNS = [
        (r'(password|passwd|secret|api_key|db_password)\s*=\s*["\'][^"\']+["\']',
         "failure", "Hardcoded credential"),
        (r'SECRET_KEY\s*=\s*["\']',
         "failure", "Hardcoded secret key"),
        (r'f["\'].*SELECT.*\{',
         "failure", "SQL injection via f-string"),
        (r'hashlib\.(md5|sha1)\s*\(',
         "failure", "Insecure hash algorithm (MD5/SHA1)"),
        (r'\beval\s*\(|\bexec\s*\(',
         "warning", "Dangerous built-in: eval/exec"),
        (r'subprocess\.(call|run|Popen).*shell\s*=\s*True',
         "failure", "Shell injection risk"),
    ]

    annotations = []
    current_file = None
    current_line = 0

    for raw_line in diff.split("\n"):
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:].strip()
            current_line = 0
        elif raw_line.startswith("@@ "):
            m = re.search(r'\+(\d+)', raw_line)
            if m:
                current_line = int(m.group(1)) - 1
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            current_line += 1
            content = raw_line[1:]
            for pattern, level, ann_title in PATTERNS:
                if re.search(pattern, content, re.IGNORECASE) and current_file:
                    annotations.append({
                        "path": current_file,
                        "start_line": current_line,
                        "end_line": current_line,
                        "annotation_level": level,
                        "title": ann_title,
                        "message": content.strip(),
                    })
                    break  # one annotation per line
        elif raw_line and not raw_line.startswith("-") and not raw_line.startswith("\\"):
            current_line += 1

    return annotations[:50]


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
