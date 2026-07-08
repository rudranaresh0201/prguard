from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.core.logging import get_logger
from backend.cross_repo_store import announce_change, check_symbols

logger = get_logger(__name__)

router = APIRouter(prefix="/cross-repo", tags=["cross-repo"])


class AnnounceRequest(BaseModel):
    repo: str = Field(..., description='e.g. "myorg/repo-a"')
    symbol: str = Field(..., description='The function, class, or endpoint name that changed, e.g. "charge" or "POST /v1/payments"')
    old_signature: str = Field(default="", description='e.g. "charge(amount)"')
    new_signature: str = Field(default="", description='e.g. "charge(amount, currency)"')
    summary: str = Field(default="", description="One-sentence human summary of the change")
    severity: str = Field(default="medium", description='"low" | "medium" | "high" | "critical"')
    pr_url: str = Field(default="", description="Link to the PR that introduced the change")


class AnnounceResponse(BaseModel):
    id: int
    status: str = "announced"


class CheckRequest(BaseModel):
    repo: str = Field(..., description='The repo doing the check, e.g. "myorg/repo-b" — excluded from its own results')
    symbols: list[str] = Field(..., description='Function/class/endpoint names this repo imports or calls from elsewhere')
    expected_repos: dict[str, str] = Field(
        default_factory=dict,
        description=(
            'Optional: {"symbol": "owning/repo"} for symbols where you know the source repo. '
            "Symbol names are global on this board, not namespaced per repo — two unrelated repos "
            'could both define e.g. "charge". Scoping a symbol here avoids matching an unrelated '
            "repo's same-named symbol. Symbols omitted here match any repo (default behavior)."
        ),
    )


class BreakingChangeHit(BaseModel):
    id: int
    repo: str
    symbol: str
    old_signature: str
    new_signature: str
    summary: str
    severity: str
    pr_url: str
    announced_at: float


class CheckResponse(BaseModel):
    affected: bool
    changes: list[BreakingChangeHit]


@router.post("/announce", response_model=AnnounceResponse)
async def announce(req: AnnounceRequest) -> AnnounceResponse:
    """Announce a breaking change so other repos can discover it.

    Call this the moment your own PR review pipeline detects a breaking
    change (e.g. PRGuard's ``api_change_node`` flags ``breaking_changes:
    True``). No prior registration or shared secret needed — any repo can
    announce.

    Example::

        POST /cross-repo/announce
        {
          "repo": "myorg/repo-a",
          "symbol": "charge",
          "old_signature": "charge(amount)",
          "new_signature": "charge(amount, currency)",
          "summary": "charge() now requires an explicit currency",
          "severity": "high",
          "pr_url": "https://github.com/myorg/repo-a/pull/42"
        }
    """
    change_id = announce_change(
        repo=req.repo,
        symbol=req.symbol,
        old_signature=req.old_signature,
        new_signature=req.new_signature,
        summary=req.summary,
        severity=req.severity,
        pr_url=req.pr_url,
    )
    logger.info("[CrossRepo] %s announced breaking change to %s (id=%s)", req.repo, req.symbol, change_id)
    return AnnounceResponse(id=change_id)


@router.post("/check", response_model=CheckResponse)
async def check(req: CheckRequest) -> CheckResponse:
    """Check whether any symbol your repo depends on has a pending breaking change.

    Call this from your own PR review pipeline before merging, passing the
    function/class/endpoint names your diff imports or calls from other
    repos. Your own repo's announcements are excluded from the results.

    Example::

        POST /cross-repo/check
        {
          "repo": "myorg/repo-b",
          "symbols": ["charge", "refund"],
          "expected_repos": {"charge": "myorg/repo-a"}
        }
    """
    hits = check_symbols(req.symbols, exclude_repo=req.repo, expected_repos=req.expected_repos)
    logger.info("[CrossRepo] %s checked %d symbols, %d hits", req.repo, len(req.symbols), len(hits))
    return CheckResponse(
        affected=len(hits) > 0,
        changes=[BreakingChangeHit(**hit) for hit in hits],
    )
