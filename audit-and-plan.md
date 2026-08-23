# prguard — Repo Audit, Fixes Applied

## Fixed and pushed (2026-08-23)

Removed:
- `rag-/` — an entire unrelated old project ("RAGnosis") accidentally committed
  inside this repo (`.env.example`, `Dockerfile`, `README.md`, `render.yaml`,
  `app.py`, `package-lock.json`) — 7 files, same copy-paste-contamination
  pattern already found and cleaned up in `agentic-rag`.

Fixed:
- `.env.example`: `OPENROUTER_API_KEY=OPENROUTER_API_KEY=...` → single key
  (same duplicated-key-name bug as agentic-rag's `.env.example`). Also
  replaced the plausible-looking placeholder `API_KEY=mysecretkey123` with an
  obvious placeholder (`your-api-key-here`) so nobody mistakes it for a real
  default.
- `README.md`: setup instructions said `git clone .../rag-` and `cd rag-` —
  pointed at the wrong repo entirely (leftover from copy-pasting the
  agentic-rag README as a template). Fixed to `prguard`.
- `README.md`: "Review time: ~13 seconds" was false. The pipeline has
  `time.sleep(8)` calls in 4 always-run nodes (security, docs, bugs,
  api_change) to stay within Groq's TPM rate limit — that's 32+ seconds of
  sleep alone before any LLM latency. Corrected to "~1-2 minutes (includes
  intentional per-node delays to stay within Groq's rate limits)".
- `backend/cross_repo_store.py::check_symbols()` — **real bug, not cosmetic**:
  `ORDER BY announced_at DESC` had no tiebreaker. Two `announce_change()`
  calls made back-to-back can land on the same `time.time()` value (coarse
  clock resolution), making "most recent per symbol" undefined — confirmed
  by actually running the test suite twice and watching
  `test_check_returns_most_recent_announcement_per_symbol` fail
  intermittently (17/17 pass, then 16/17, then 17/17 again). Fixed by adding
  `, id DESC` as a secondary sort key. Verified deterministic across 5
  consecutive full test runs after the fix.

Net: cleaner repo root, two false claims corrected, one real
non-deterministic bug fixed with a verified repro.

## Still open, not fixed this pass

1. **No CI** (`.github/workflows` absent). Tests exist and are good (17
   tests on the Aftershock signing/store logic) but nothing runs them
   automatically on push/PR. Highest remaining CV-value item.
2. **No test coverage on the governance pipeline itself**
   (`backend/governance/nodes.py`, `graph.py`) — the 17 tests only cover
   Aftershock (the cross-repo board). The 8-agent LangGraph pipeline that's
   the actual headline feature has zero automated tests; the "100%
   recall / 94.12% precision" numbers come from a one-time manual PR #10
   evaluation, not a repeatable test. Not fabricated — the git history shows
   real iteration (68.75% → 75% → 100% across 3 commits) — but it's a
   one-shot number, not a regression-tested one.
3. **`demo.ps1` and `demo_script.sh`** were untracked (not committed) despite
   being real, working demo scripts that hit the live deployed endpoint
   (`governance-agent.onrender.com`, confirmed reachable, HTTP 200 on
   `/cross-repo/health`). Worth committing — they're genuinely useful, not
   scratch files.
4. **Ed25519 signing/storage (Aftershock) is solid** — no issues found.
   Canonical JSON signing, offline-verifiable via `verify_with_key`, key
   persists across restarts via a configurable path, SQLite migration
   handles pre-signing-era rows gracefully (`sig` nullable). This is the
   strongest, most defensible part of the repo.
5. **Known, documented limitation, not a bug**: `announce` has no
   authentication on who can post for a given `repo` name — anyone can
   announce a breaking change under any repo's identity. This is called out
   explicitly in `SKILL.md` as a deliberate tradeoff (no prior credential
   exchange needed), not an oversight — fine to state as-is in an interview,
   including *why* it's a deliberate tradeoff.

## Repo hygiene notes

- Git history here is real incremental commits (23+ commits shown in
  `git log`, each a real named change — "fix: improve recall to 85%+",
  "feat: 8-agent enterprise pipeline", etc.), unlike agentic-rag's single
  squashed commit. This repo's history alone is a legitimate thing to point
  to as evidence of real iterative work.
- Live demo (`governance-agent.onrender.com`) is actually deployed and
  responding — confirmed via a live health-check request, not just claimed.
