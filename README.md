# swe-agentic-loop

An installable **agent skill** that runs a two-tier, multi-agent software engineering loop:
a fast **Coder** and **Reviewer** iterate in an inner loop, then a `claude-opus-5`
**Executive Reviewer** performs an architectural and security audit in an outer loop.
The loop runs until both tiers approve, or until iteration caps are hit.

It is **stack-agnostic** — the orchestrator detects your project's own test, lint, and build
commands at runtime instead of assuming a toolchain.

```
Coder ──diff──► Reviewer ──APPROVED──► Executive Reviewer ──APPROVED──► Converged
  ▲                 │                          │
  └──── defects ────┘◄──── executive findings ─┘
```

## Install

### Option A — install script

```bash
git clone git@github.com:msebastianb/swe-agentic-loop.git
cd swe-agentic-loop
./install.sh
```

By default this installs to `~/.copilot/skills/swe-agentic-loop` (user scope, available in
every repository). Use `--project` to install into the current repository's
`.github/skills/` directory instead, or `--dir <path>` for a custom skills root.

```bash
./install.sh --project          # install into ./.github/skills
./install.sh --dir ~/.claude/skills
```

### Option B — manual

Copy `skills/swe-agentic-loop/` into your agent's skills directory:

| Agent | Skills directory |
| :--- | :--- |
| GitHub Copilot CLI (user scope) | `~/.copilot/skills/` |
| GitHub Copilot (project scope) | `<repo>/.github/skills/` |
| Claude Code (user scope) | `~/.claude/skills/` |
| Claude Code (project scope) | `<repo>/.claude/skills/` |

```bash
cp -R skills/swe-agentic-loop ~/.copilot/skills/
```

Restart your agent session so the skill is picked up.

## Models

The skill pins specific models per host runtime, so the inner loop stays cheap while the
executive audit gets full reasoning power.

| Runtime | Coder + Reviewer (inner) | Executive Reviewer (outer) |
| :--- | :--- | :--- |
| **GitHub Copilot CLI** | `gemini-3.6-flash` — effort `medium` | `claude-opus-5` — effort `high` |
| **Claude Code** | `claude-opus-5` — thinking `low` | `claude-opus-5` — thinking `high` |

If a model is unavailable in the runtime, the orchestrator falls back down a generic tier list
(`gemini-3.5-flash` → `gpt-5.4-mini` → `claude-haiku-4.5` for the inner loop; `claude-opus-4.8`
→ `gpt-5.6-sol` → `claude-sonnet-5` for the executive) and, as a last resort, omits the field
entirely. Whatever actually ran is disclosed in the final report.

## Usage

Once installed, trigger it by intent or by name:

- "run the agentic loop on the auth refactor"
- "start agents and make them talk"
- "/swe-agentic-loop"

The orchestrator will:

1. Detect the host runtime (model matrix) and your repository's toolchain and test commands.
2. Ask once whether tests should run in the loop, or be skipped for speed.
3. Spawn `reviewer-agent` and `executive-reviewer-agent`, then `coder-agent`, and bind their IDs.
4. Iterate: Coder implements → Reviewer audits the `git diff` and runs targeted tests.
5. On inner approval, hand the diff to the Executive Reviewer for an architecture/security audit.
6. Route any executive findings back to the Coder and re-enter the inner loop.
7. Print a final summary with the audit trail once both tiers approve.

## Requirements

- An agent runtime that supports sub-agents and inter-agent messaging
  (`task`, `write_agent`, `read_agent`, `list_agents`).
- A `git` repository (diff-based review degrades gracefully without one).

## Safety controls

- Inner loop capped at 10 iterations; outer loop capped at 10 cycles; 3 full outer resets max.
- Working directory is checked before starting; stashing requires your confirmation.
- Test failures are blocking defects.
- Secrets detected in a diff cause an immediate rejection and are surfaced to you.
- No new test framework is ever installed to satisfy the loop.

## License

MIT — see [LICENSE](LICENSE).
