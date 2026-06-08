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
