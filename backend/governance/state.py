from typing import TypedDict, Annotated, Literal, Optional
from langgraph.graph.message import add_messages

class PRState(TypedDict):
    # PR metadata
    pr_number: int
    repo: str
    title: str
    body: str
    diff: str
    author: str
    base_branch: str
    head_branch: str

    # Gate results
    security_result: dict
    test_result: dict
    docs_result: dict
    policy_result: dict

    # Decision
    gates_passed: bool
    blocking_issues: list[str]
    warnings: list[str]

    # Actions taken
    comments_posted: list[str]
    approval_requested: bool
    approved_by: Optional[str]
    merged: bool

    # Context retrieval
    touched_modules: list[str]
    code_context: list[dict]
    policy_context: list[dict]

    # Audit
    agent_steps: list[str]
    audit_log: list[dict]

    # GitHub Checks API — maps check name to check run ID (empty if checks:write unavailable)
    check_run_ids: dict

    # Error tracking
    errors: list[str]

    # Triage outputs
    risk_level: str
    risk_reason: str
    triage_passed: bool

    # Security outputs (top-level, populated on both success and LLM error)
    security_passed: bool
    security_issues: str
    security_severity: str
    security_details: str
    security_fixes: list[str]
    security_fix_suggestions: list

    # Docs outputs (top-level, populated on both success and LLM error)
    docs_passed: bool
    docs_missing: str
    docs_suggestions: str

    # Auth
    github_token: str
