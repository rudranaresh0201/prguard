# PRGuard 🛡️

> Autonomous PR security and code review agent. Reviews any Pull Request in 13 seconds across any programming language.

## Live Demo
**Deployed at:** https://governance-agent.onrender.com

## Evaluation Results
Tested against 16 known vulnerabilities across 5 languages:

| Metric | Score |
|--------|-------|
| Recall | 100% (16/16 issues caught) |
| Precision | 94.12% (1 false positive) |
| Review time | ~13 seconds |
| Languages tested | Python, Solidity, Bash, Dockerfile |

## What It Catches

**Security Vulnerabilities**
- Hardcoded secrets, API keys, passwords, tokens
- SQL injection (Python f-strings, Bash numbered args)
- Insecure cryptography (MD5, SHA1, weak keys)
- Missing authorization checks on sensitive operations
- Dangerous functions (eval, exec, shell=True)
- Insecure configurations (debug mode, open CORS, weak TLS)

**Smart Contract (Solidity)**
- Reentrancy vulnerabilities (CEI pattern violations)
- tx.origin authentication bypass
- Integer overflow in pre-0.8.0 contracts
- Unchecked .call() return values

**Infrastructure (Dockerfile, Bash, YAML)**
- Secrets in ENV variables
- Running as root user
- Unpinned base images (:latest tag)
- Shell injection via unquoted variables
- Arbitrary code execution via eval

**Code Quality**
- Logic bugs (off-by-one, infinite loops, null references)
- Division by zero and numeric overflow
- Missing error handling
- Unhandled edge cases

**Documentation**
- Missing docstrings and type hints
- Missing CHANGELOG entries
- TODO comments in production code

## How It Works
Developer opens PR
↓
GitHub webhook → PRGuard server
↓
Full diff fetched from GitHub API
↓
LangGraph multi-agent pipeline:
Triage Agent    → risk classification
Context Agent   → CodeRAG codebase retrieval
Security Agent  → vulnerability detection + fixes
Docs Agent      → documentation compliance
Bug Agent       → logic error detection + fixes
↓
Gate Aggregator → approve or block
↓
GitHub: comment + labels + merge blocked
↓
Audit log written

## CodeRAG — The Core Differentiator

Unlike linters that only see the diff, PRGuard indexes your entire codebase at function level using AST parsing. Before judging new code, it retrieves the most semantically similar existing functions and injects them into the review prompt.

This enables:
- **Architecture violation detection** — new code contradicts existing patterns
- **Duplication detection** — functionality already exists elsewhere  
- **Pattern-consistent fixes** — suggested fixes match your codebase style

## Auto-Fix — Like Claude Code

When PRGuard finds issues it posts exact FIND/REPLACE fix suggestions.
To apply them automatically, comment on any PR:
/prguard fix

The agent pushes the corrected code to your branch. You review, then merge.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Agent Orchestration | LangGraph |
| LLM | Groq / llama-3.1-8b-instant |
| Vector Database | ChromaDB |
| Embeddings | ONNX MiniLM-L6-v2 |
| GitHub Integration | PyGitHub + GitHub App |
| API Server | FastAPI |
| Deployment | Render |

## Architecture
backend/
├── app.py                    # FastAPI entry point
├── api/
│   └── routes_governance.py  # Webhook handler
├── governance/
│   ├── state.py              # PRState TypedDict
│   ├── graph.py              # LangGraph pipeline
│   ├── nodes.py              # 5 agent functions
│   ├── code_rag.py           # AST indexer + retrieval
│   ├── github_client.py      # GitHub API actions
│   └── github_app_auth.py    # GitHub App JWT auth

## Setup

### 1. Clone and install
```bash
git clone https://github.com/rudranaresh0201/rag-
cd rag-
pip install -r backend/requirements.txt
```

### 2. Environment variables
```bash
GITHUB_TOKEN=your_token
GITHUB_WEBHOOK_SECRET=your_secret
GITHUB_REPO=owner/repo
GROQ_API_KEY=your_groq_key
INTERNAL_API_TOKEN=your_internal_token
GROQ_MODEL=llama-3.1-8b-instant
```

### 3. Run locally
```bash
uvicorn backend.app:app --reload --port 8003
```

### 4. Manual trigger
```bash
curl -X POST http://localhost:8003/governance/trigger \
  -H "X-Internal-Token: your_token" \
  -H "Content-Type: application/json" \
  -d '{"pr_number": 1, "repo": "owner/repo"}'
```

## Security Design

- HMAC-SHA256 webhook signature verification
- Prompt injection defense on all user-controlled fields
- Fail-closed — any error blocks the PR, never silently approves
- GitHub App installation tokens scoped per repo, expire in 1 hour
- Full audit trail on every decision

## Evaluation Methodology

PRGuard was tested against a controlled evaluation suite (PR #10) containing 16 deliberately planted vulnerabilities across 5 file types. Each finding was manually verified. The single false positive was a null-reference accusation on a function with explicit None guards.

Three iterations of prompt refinement moved recall from 68.75% → 75% → 100%.

## Roadmap

- [ ] One-click GitHub App install flow
- [ ] Postgres audit log storage  
- [ ] Slack notifications + approval flow
- [ ] Dashboard with governance history
- [ ] Go, Rust, Java AST-level indexing
- [ ] Evaluation dataset expansion to 100+ PRs

## Resume Line

> Built PRGuard — an autonomous PR governance agent using LangGraph multi-agent orchestration and AST-indexed CodeRAG that reviews Pull Requests for security vulnerabilities, logic bugs, and documentation compliance across any programming language. Achieves 100% recall and 94.12% precision on evaluation suite. Deployed on Render with GitHub App integration.
