from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv
load_dotenv(override=True)
import hmac
import hashlib
import os
import json

from backend.governance.graph import governance_graph
from backend.governance.state import PRState
from backend.governance.github_client import get_pr_details, get_pr_diff
from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/governance", tags=["governance"])

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    if not GITHUB_WEBHOOK_SECRET:
        return True  # skip verification in dev
    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

async def run_governance_pipeline(pr_number: int, repo: str):
    try:
        details = get_pr_details(pr_number)
        diff = get_pr_diff(pr_number)

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
        }

        result = await governance_graph.ainvoke(initial_state)

        logger.info("[Governance] PR #%s complete", pr_number)
        logger.info("[Governance] Steps: %s", result['agent_steps'])
        logger.info("[Governance] Gates passed: %s", result['gates_passed'])
        logger.info("[Governance] Merged: %s", result['merged'])

    except Exception as e:
        logger.exception("[Governance] ERROR on PR #%s: %s", pr_number, e)
        raise

@router.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload_bytes = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_webhook_signature(payload_bytes, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(payload_bytes)
    event = request.headers.get("X-GitHub-Event", "")

    if event == "pull_request":
        action = payload.get("action", "")
        if action in ["opened", "synchronize", "reopened"]:
            pr_number = payload["pull_request"]["number"]
            repo = payload["repository"]["full_name"]
            logger.info("[Governance] PR #%s %s — starting pipeline", pr_number, action)
            background_tasks.add_task(run_governance_pipeline, pr_number, repo)
            return {"status": "accepted", "pr": pr_number, "action": action}

    return {"status": "ignored", "event": event}

@router.post("/trigger/{pr_number}")
async def manual_trigger(pr_number: int, background_tasks: BackgroundTasks):
    """Manually trigger governance pipeline for a PR — for testing."""
    repo = os.getenv("GITHUB_REPO")
    background_tasks.add_task(run_governance_pipeline, pr_number, repo)
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
