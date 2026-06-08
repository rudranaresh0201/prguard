import os
import subprocess
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(override=True)

from langchain_groq import ChatGroq
from backend.config import GROQ_MODEL
from backend.governance.state import PRState
from backend.governance.github_client import post_pr_comment, add_pr_label, get_pr_details

llm = ChatGroq(model=GROQ_MODEL, api_key=os.getenv("GROQ_API_KEY"))

def log_step(state: PRState, agent: str, action: str, result: str) -> dict:
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent": agent,
        "action": action,
        "result": result,
        "pr_number": state["pr_number"]
    }
    return entry

# ── 1. Triage Node ─────────────────────────────────────────
def triage_node(state: PRState) -> PRState:
    prompt = f"""Analyze this PR and classify its risk level.
Title: {state['title']}
Author: {state['author']}
Diff preview: {state['diff'][:2000]}

Respond in exactly this format:
RISK: low|medium|high
TYPE: feature|bugfix|refactor|docs|config|security
SUMMARY: one line summary"""

    result = llm.invoke(prompt).content.strip()
    lines = {l.split(":")[0].strip(): ":".join(l.split(":")[1:]).strip()
             for l in result.split("\n") if ":" in l}

    risk = lines.get("RISK", "medium")
    pr_type = lines.get("TYPE", "feature")
    summary = lines.get("SUMMARY", state["title"])

    comment = f"""## Governance Agent — PR Triage
**Risk Level:** {risk.upper()}
**Type:** {pr_type}
**Summary:** {summary}

Running automated gates..."""

    post_pr_comment(state["pr_number"], comment)
    add_pr_label(state["pr_number"], f"risk:{risk}")
    add_pr_label(state["pr_number"], f"type:{pr_type}")

    audit_entry = log_step(state, "triage_node", "classify_pr", f"risk={risk} type={pr_type}")

    return {
        **state,
        "agent_steps": state["agent_steps"] + [f"🔍 Triage → risk:{risk} type:{pr_type}"],
        "audit_log": state["audit_log"] + [audit_entry],
        "warnings": state["warnings"] + ([f"High risk PR — extra scrutiny applied"] if risk == "high" else [])
    }


# ── 1.5 Context Retrieval Node ─────────────────────────────
def context_retrieval_node(state: PRState) -> PRState:
    from backend.governance.code_rag import (
        retrieve_similar_code,
        extract_modules_from_diff
    )
    from backend.retrieval import retrieve_chunks

    diff = state["diff"]
    title = state["title"]

    # Step 1 — identify touched modules
    modules = extract_modules_from_diff(diff)

    # Step 2 — retrieve similar existing code
    code_query = f"{title} {' '.join(modules)}"
    code_context = retrieve_similar_code(code_query, top_k=5)

    # Step 3 — retrieve architecture policies from your existing RAG
    policy_context = []
    try:
        policy_result = retrieve_chunks(
            query=f"{' '.join(modules)} architecture policy security requirements",
            top_k=5
        )
        policy_context = policy_result.get("chunks", [])
    except Exception:
        pass

    # Step 4 — log what was retrieved
    code_files = list(set([c["file"].split("/")[-1] for c in code_context]))
    audit_entry = log_step(
        state, "context_retrieval_node", "retrieve_context",
        f"modules={modules} code_chunks={len(code_context)} policy_chunks={len(policy_context)}"
    )

    return {
        **state,
        "touched_modules": modules,
        "code_context": code_context,
        "policy_context": policy_context,
        "agent_steps": state["agent_steps"] + [
            f"🔎 Context → modules:{modules} code:{len(code_context)} policy:{len(policy_context)}"
        ],
        "audit_log": state["audit_log"] + [audit_entry],
    }


# ── 2. Security Node ────────────────────────────────────────
def security_node(state: PRState) -> PRState:
    diff = state["diff"]

    # LLM security review
    prompt = f"""You are a security code reviewer. Analyze this diff for security issues.
Look for: hardcoded secrets, SQL injection, XSS, insecure dependencies, missing auth, exposed endpoints.

Diff:
{diff[:3000]}

Respond in exactly this format:
VERDICT: pass|fail
ISSUES: comma-separated list of issues found, or 'none'
SEVERITY: low|medium|high|critical"""

    result = llm.invoke(prompt).content.strip()
    lines = {l.split(":")[0].strip(): ":".join(l.split(":")[1:]).strip()
             for l in result.split("\n") if ":" in l}

    verdict = lines.get("VERDICT", "pass")
    issues = lines.get("ISSUES", "none")
    severity = lines.get("SEVERITY", "low")

    if verdict == "fail":
        comment = f"""## Security Gate — FAILED
**Severity:** {severity.upper()}
**Issues Found:**
{chr(10).join(f'- {i.strip()}' for i in issues.split(','))}

Please fix these security issues before this PR can be merged."""
        post_pr_comment(state["pr_number"], comment)
        add_pr_label(state["pr_number"], "security:failed")
    else:
        comment = "## Security Gate — PASSED\nNo security issues detected."
        post_pr_comment(state["pr_number"], comment)
        add_pr_label(state["pr_number"], "security:passed")

    audit_entry = log_step(state, "security_node", "security_review", f"verdict={verdict} severity={severity}")
    blocking = verdict == "fail" and severity in ["high", "critical"]

    return {
        **state,
        "security_result": {"verdict": verdict, "issues": issues, "severity": severity},
        "blocking_issues": state["blocking_issues"] + ([f"Security: {issues}"] if blocking else []),
        "agent_steps": state["agent_steps"] + [f"🔒 Security → {verdict.upper()}"],
        "audit_log": state["audit_log"] + [audit_entry],
    }


# ── 3. Docs Node ────────────────────────────────────────────
def docs_node(state: PRState) -> PRState:
    prompt = f"""Review this PR diff for documentation compliance.
Check: docstrings on new functions, CHANGELOG updated, README updated if needed, inline comments on complex logic.

Diff:
{state['diff'][:3000]}

Respond in exactly this format:
VERDICT: pass|fail
MISSING: comma-separated list of missing docs, or 'none'"""

    result = llm.invoke(prompt).content.strip()
    lines = {l.split(":")[0].strip(): ":".join(l.split(":")[1:]).strip()
             for l in result.split("\n") if ":" in l}

    verdict = lines.get("VERDICT", "pass")
    missing = lines.get("MISSING", "none")

    if verdict == "fail":
        comment = f"""## Docs Gate — FAILED
**Missing Documentation:**
{chr(10).join(f'- {m.strip()}' for m in missing.split(','))}

Please add the missing documentation before merging."""
        post_pr_comment(state["pr_number"], comment)
        add_pr_label(state["pr_number"], "docs:failed")
    else:
        comment = "## Docs Gate — PASSED\nDocumentation looks complete."
        post_pr_comment(state["pr_number"], comment)
        add_pr_label(state["pr_number"], "docs:passed")

    audit_entry = log_step(state, "docs_node", "docs_review", f"verdict={verdict}")

    return {
        **state,
        "docs_result": {"verdict": verdict, "missing": missing},
        "blocking_issues": state["blocking_issues"] + ([f"Docs: {missing}"] if verdict == "fail" else []),
        "agent_steps": state["agent_steps"] + [f"📝 Docs → {verdict.upper()}"],
        "audit_log": state["audit_log"] + [audit_entry],
    }


# ── 4. Gate Aggregator Node ─────────────────────────────────
def gate_aggregator_node(state: PRState) -> PRState:
    blocking = state["blocking_issues"]
    gates_passed = len(blocking) == 0

    if gates_passed:
        comment = """## All Gates Passed
Security: PASSED
Docs: PASSED

Requesting human approval via Slack..."""
        add_pr_label(state["pr_number"], "gates:passed")
    else:
        comment = f"""## Gates Failed — Merge Blocked
**Blocking Issues:**
{chr(10).join(f'- {issue}' for issue in blocking)}

Fix all blocking issues and push a new commit to re-trigger review."""
        add_pr_label(state["pr_number"], "gates:failed")

    post_pr_comment(state["pr_number"], comment)
    audit_entry = log_step(state, "gate_aggregator", "aggregate_gates", f"passed={gates_passed} blocking={len(blocking)}")

    return {
        **state,
        "gates_passed": gates_passed,
        "agent_steps": state["agent_steps"] + [f"{'✅' if gates_passed else '❌'} Gates → {'PASSED' if gates_passed else 'FAILED'}"],
        "audit_log": state["audit_log"] + [audit_entry],
    }


# ── 5. Merge Node ───────────────────────────────────────────
def merge_node(state: PRState) -> PRState:
    from backend.governance.github_client import merge_pr

    result = merge_pr(
        state["pr_number"],
        commit_message=f"Merged by Governance Agent — all gates passed"
    )

    comment = f"""## PR Merged by Governance Agent
All gates passed. PR merged autonomously.
Commit: {result.get('sha', 'N/A')}"""
    post_pr_comment(state["pr_number"], comment)

    audit_entry = log_step(state, "merge_node", "merge_pr", f"merged={result.get('merged')} sha={result.get('sha')}")

    return {
        **state,
        "merged": result.get("merged", False),
        "agent_steps": state["agent_steps"] + ["🚀 Merged → PR merged autonomously"],
        "audit_log": state["audit_log"] + [audit_entry],
    }


# ── 6. No-Merge Node ────────────────────────────────────────
def no_merge_node(state: PRState) -> PRState:
    audit_entry = log_step(state, "no_merge_node", "block_merge", f"blocking_issues={state['blocking_issues']}")
    return {
        **state,
        "merged": False,
        "agent_steps": state["agent_steps"] + ["🚫 Merge blocked — fix issues and re-push"],
        "audit_log": state["audit_log"] + [audit_entry],
    }


# ── 7. Audit Node ────────────────────────────────────────────
def audit_node(state: PRState) -> PRState:
    import json, os
    from datetime import datetime

    audit_data = {
        "pr_number": state["pr_number"],
        "repo": state["repo"],
        "title": state["title"],
        "author": state["author"],
        "timestamp": datetime.utcnow().isoformat(),
        "gates_passed": state["gates_passed"],
        "merged": state["merged"],
        "blocking_issues": state["blocking_issues"],
        "warnings": state["warnings"],
        "agent_steps": state["agent_steps"],
        "security_result": state["security_result"],
        "docs_result": state["docs_result"],
        "touched_modules": state["touched_modules"],
    }

    os.makedirs("audit_logs", exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_path = f"audit_logs/pr_{state['pr_number']}_{timestamp}.json"
    with open(log_path, "w") as f:
        json.dump(audit_data, f, indent=2)

    audit_entry = log_step(state, "audit_node", "write_audit_log", f"path={log_path}")
    return {
        **state,
        "agent_steps": state["agent_steps"] + [f"Audit log saved: {log_path}"],
        "audit_log": state["audit_log"] + [audit_entry],
    }
