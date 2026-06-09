from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Header, Depends
from dotenv import load_dotenv
load_dotenv(override=True)
import hmac
import hashlib
import os
import json
from typing import Optional
from pydantic import BaseModel, validator

from backend.governance.graph import run_pipeline_with_recovery
from backend.governance.state import PRState
from backend.governance.github_client import get_pr_details, fetch_pr_diff, create_check_run
from backend.governance.github_app_auth import get_installation_token
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/governance", tags=["governance"])

_secret = os.getenv("GITHUB_WEBHOOK_SECRET")
if not _secret:
    raise RuntimeError("GITHUB_WEBHOOK_SECRET env var must be set before starting the server")
GITHUB_WEBHOOK_SECRET: str = _secret

_internal_token = os.getenv("INTERNAL_API_TOKEN")
if not _internal_token:
    raise RuntimeError("INTERNAL_API_TOKEN env var must be set before starting the server")
INTERNAL_API_TOKEN: str = _internal_token

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not signature:
        return False
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

async def run_governance_pipeline(
    pr_number: int,
    repo: str,
    diff: str,
    installation_id: int = None,
):
    try:
        if installation_id:
            from backend.governance.github_app_auth import get_installation_token
            token = get_installation_token(installation_id)
        else:
            token = os.getenv("GITHUB_TOKEN")

        details = get_pr_details(pr_number, token=token)

        # Create all governance check runs upfront so they show as in_progress together.
        # Silently skips if GITHUB_TOKEN lacks checks:write (labels/comments still work).
        check_run_ids: dict = {}
        head_sha = details.get("head_sha", "")
        if head_sha:
            for check_name in ("governance/triage", "governance/security", "governance/docs"):
                try:
                    check_run_ids[check_name] = create_check_run(check_name, head_sha)
                except Exception:
                    logger.warning(
                        "[Governance] Could not create check run '%s' — checks:write permission required",
                        check_name,
                    )

        initial_state: PRState = {
            "pr_number": pr_number,
            "repo": repo,
            "title": details["title"],
            "body": details["body"],
            "diff": diff,
            "author": details["author"],
            "base_branch": details["base_branch"],
            "head_branch": details["head_branch"],
            "security_result": {},
            "test_result": {},
            "docs_result": {},
            "policy_result": {},
            "gates_passed": False,
            "blocking_issues": [],
            "warnings": [],
            "comments_posted": [],
            "approval_requested": False,
            "approved_by": None,
            "merged": False,
            "touched_modules": [],
            "code_context": [],
            "policy_context": [],
            "agent_steps": [],
            "audit_log": [],
            "check_run_ids": check_run_ids,
            "errors": [],
            "risk_level": "",
            "risk_reason": "",
            "triage_passed": False,
            "security_passed": False,
            "security_issues": "",
            "security_severity": "",
            "security_details": "",
            "docs_passed": False,
            "docs_missing": "",
            "docs_suggestions": "",
            "github_token": token or "",
        }

        result = await run_pipeline_with_recovery(pr_number, repo, initial_state)

        if result:
            logger.info("[Governance] PR #%s complete", pr_number)
            logger.info("[Governance] Steps: %s", result['agent_steps'])
            logger.info("[Governance] Gates passed: %s", result['gates_passed'])
            logger.info("[Governance] Merged: %s", result['merged'])

    except Exception as e:
        logger.exception("[Governance] ERROR building state for PR #%s: %s", pr_number, e)
        raise

async def verify_internal_token(x_internal_token: str = Header(None)):
    if not x_internal_token:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not hmac.compare_digest(x_internal_token, INTERNAL_API_TOKEN):
        raise HTTPException(status_code=403, detail="Forbidden")


class TriggerRequest(BaseModel):
    pr_number: int
    repo: Optional[str] = None

    @validator("pr_number")
    def pr_number_positive(cls, v):
        if v <= 0:
            raise ValueError("pr_number must be positive")
        return v

    @validator("repo")
    def repo_format(cls, v):
        if v is not None:
            import re
            if not re.match(r'^[\w.\-]+/[\w.\-]+$', v):
                raise ValueError("repo must be in format owner/name")
        return v


@router.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload_bytes = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_webhook_signature(payload_bytes, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(payload_bytes)
    event = request.headers.get("X-GitHub-Event", "")
    installation_id = payload.get("installation", {}).get("id")

    if event == "installation":
        action = payload.get("action")
        repos = payload.get("repositories", [])
        logger.info(
            "[Governance] App %s installation_id=%s repos=%s",
            action, installation_id, [r["full_name"] for r in repos]
        )
        return {"status": "ok", "action": action}

    if event == "pull_request":
        action = payload.get("action", "")
        if action in ["opened", "synchronize", "reopened"]:
            pr_number = payload["pull_request"]["number"]
            repo = payload["repository"]["full_name"]
            if installation_id:
                try:
                    webhook_token = get_installation_token(installation_id)
                except Exception:
                    webhook_token = os.getenv("GITHUB_TOKEN")
            else:
                webhook_token = os.getenv("GITHUB_TOKEN")
            try:
                diff = fetch_pr_diff(pr_number, token=webhook_token, repo_name=repo)
            except Exception:
                logger.exception("[Governance] Failed to fetch diff for PR #%s", pr_number)
                diff = "[DIFF FETCH FAILED]"
            logger.info("[Governance] PR #%s %s — starting pipeline", pr_number, action)
            background_tasks.add_task(
                run_governance_pipeline, pr_number, repo, diff, installation_id
            )
            return {"status": "accepted", "pr": pr_number, "action": action}

    return {"status": "ignored", "event": event}

@router.post("/trigger")
async def manual_trigger(
    body: TriggerRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_internal_token),
):
    pr_number = body.pr_number
    repo = body.repo or os.getenv("GITHUB_REPO")
    if not repo:
        raise HTTPException(status_code=400, detail="repo not provided and GITHUB_REPO not set")
    try:
        diff = fetch_pr_diff(pr_number)
    except Exception:
        logger.exception("[Governance] Failed to fetch diff for PR #%s", pr_number)
        diff = "[DIFF FETCH FAILED]"
    background_tasks.add_task(run_governance_pipeline, pr_number, repo, diff)
    return {"status": "triggered", "pr": pr_number, "repo": repo}

@router.post("/start-tunnel")
async def start_tunnel():
    from pyngrok import ngrok, conf
    authtoken = os.getenv("NGROK_AUTHTOKEN")
    if not authtoken:
        raise HTTPException(status_code=400, detail="NGROK_AUTHTOKEN not set in .env")
    conf.get_default().auth_token = authtoken
    tunnel = ngrok.connect(8003)
    public_url = tunnel.public_url
    webhook_url = f"{public_url}/governance/webhook"
    return {"tunnel_url": public_url, "webhook_url": webhook_url}

@router.post("/setup-webhook")
async def setup_webhook(webhook_url: str):
    from backend.governance.github_client import get_repo
    import os
    repo = get_repo()
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "governance-secret")

    # Remove existing governance webhooks
    for hook in repo.get_hooks():
        if "governance" in hook.config.get("url", ""):
            hook.delete()

    hook = repo.create_hook(
        name="web",
        config={
            "url": webhook_url,
            "content_type": "json",
            "secret": secret
        },
        events=["pull_request"],
        active=True
    )
    return {"status": "created", "hook_id": hook.id, "url": webhook_url}

@router.get("/health")
async def governance_health():
    from backend.governance.code_rag import get_code_collection
    col = get_code_collection()
    return {
        "status": "ok",
        "codebase_chunks": col.count(),
    }
