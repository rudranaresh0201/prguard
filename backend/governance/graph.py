import asyncio
import logging
import re

from langgraph.graph import StateGraph, END
from backend.governance.state import PRState
from backend.governance.github_client import (
    post_pr_comment, add_pr_label,
    get_file_content, push_file_fix, get_pr_details,
)
from backend.governance.nodes import (
    triage_node,
    context_retrieval_node,
    security_node,
    docs_node,
    gate_aggregator_node,
    merge_node,
    no_merge_node,
    audit_node,
)

def gates_decision(state: PRState) -> str:
    return "merge" if state["gates_passed"] else "no_merge"

def build_governance_graph():
    graph = StateGraph(PRState)

    graph.add_node("triage",            triage_node)
    graph.add_node("context_retrieval", context_retrieval_node)
    graph.add_node("security",          security_node)
    graph.add_node("docs",            docs_node)
    graph.add_node("gate_aggregator", gate_aggregator_node)
    graph.add_node("merge",           merge_node)
    graph.add_node("no_merge",        no_merge_node)
    graph.add_node("audit",           audit_node)

    graph.set_entry_point("triage")
    graph.add_edge("triage",            "context_retrieval")
    graph.add_edge("context_retrieval", "security")
    graph.add_edge("security",  "docs")
    graph.add_edge("docs",      "gate_aggregator")

    graph.add_conditional_edges(
        "gate_aggregator",
        gates_decision,
        {"merge": "merge", "no_merge": "no_merge"}
    )

    graph.add_edge("merge",    "audit")
    graph.add_edge("no_merge", "audit")
    graph.add_edge("audit",    END)

    return graph.compile()

governance_graph = build_governance_graph()

logger = logging.getLogger(__name__)


async def run_pipeline_with_recovery(pr_number: int, repo: str, initial_state: dict):
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, governance_graph.invoke, initial_state)
        return result
    except Exception as e:
        logger.exception(
            "[Governance] Pipeline failed for PR #%s repo=%s: %s",
            pr_number, repo, e
        )
        try:
            post_pr_comment(
                pr_number,
                "🚫 Governance system error — PR blocked pending manual review.\n"
                f"Error: `{type(e).__name__}`. Contact the platform team."
            )
        except Exception:
            logger.exception("[Governance] Could not post error comment for PR #%s", pr_number)
        try:
            add_pr_label(pr_number, "blocked:pipeline-error")
        except Exception:
            logger.exception("[Governance] Could not block PR #%s after pipeline error", pr_number)


async def apply_governance_fixes(pr_number: int, repo: str, token: str):
    """Apply suggested fixes when user comments /governance fix."""
    try:
        details = get_pr_details(pr_number, token=token, repo_name=repo)
        head_branch = details.get("head_branch", "")

        from github import Github
        gh = Github(token)
        repo_obj = gh.get_repo(repo)
        issue = repo_obj.get_issue(pr_number)

        fix_comment = None
        for comment in issue.get_comments():
            if "Suggested Fixes" in comment.body and "governance-bot" in comment.body:
                fix_comment = comment.body
                break

        if not fix_comment:
            post_pr_comment(
                pr_number,
                "🤖 No fix suggestions found. Run a new governance review first.",
                token=token, repo_name=repo,
            )
            return

        # Parse FIND/REPLACE_WITH blocks
        files_fixed = []
        file_blocks = re.findall(
            r'FILE: (.+?)\nFIND:\n(.+?)\nREPLACE_WITH:\n(.+?)\nEND',
            fix_comment, re.DOTALL,
        )

        for filepath, find_text, replace_text in file_blocks:
            filepath = filepath.strip()
            find_text = find_text.strip()
            replace_text = replace_text.strip()

            file_data = get_file_content(filepath, head_branch, token=token, repo_name=repo)
            if file_data.get("error"):
                continue

            current_content = file_data["content"]
            if find_text in current_content:
                new_content = current_content.replace(find_text, replace_text, 1)
                result = push_file_fix(
                    filepath=filepath,
                    new_content=new_content,
                    branch=head_branch,
                    commit_message=f"fix(governance): apply security fix in {filepath}",
                    file_sha=file_data["sha"],
                    token=token,
                    repo_name=repo,
                )
                if result["success"]:
                    files_fixed.append(filepath)

        if files_fixed:
            post_pr_comment(
                pr_number,
                f"✅ Applied fixes to: {', '.join(f'`{f}`' for f in files_fixed)}\n\n"
                "Please review the changes. The governance agent will re-review on your next push.",
                token=token, repo_name=repo,
            )
        else:
            post_pr_comment(
                pr_number,
                "⚠️ Could not apply fixes automatically — the code may have changed. "
                "Please apply the suggested fixes manually.",
                token=token, repo_name=repo,
            )

    except Exception as e:
        logger.exception(
            "[Governance] Failed to apply fixes for PR #%s: %s", pr_number, e
        )
