# swe-agentic-loop

An installable **agent skill** that runs a two-tier, multi-agent software engineering loop:
a fast **Coder** and **Reviewer** iterate in an inner loop, then an
**Executive Reviewer** performs an architectural and security audit in an outer loop.
Before spawning anything, the skill asks you for a model and reasoning effort per role and where
to remember the choice (user profile or this session only), then presents a **Plan Gate** — a short
plan plus the task's acceptance checklist — and spawns nothing until you approve it.
The loop runs until both tiers approve, or until iteration caps are hit. All inter-agent
traffic flows through a single **message bus** — the orchestrator — so the agents never talk to each
other directly. The shared information lives in an **artifact mailbox** (a scratch directory outside
the repo, never committed); each agent is spawned stateless with **pointers** to the files it must
read and write, so no prompt re-embeds the task spec, the diff, or the history. When the runtime keeps
child sessions alive, the orchestrator probes that capability and then spawns each role **once** at the
start, each waiting on the bus with a single blocking call instead of being re-spawned every turn.

It is **stack-agnostic** — the orchestrator detects your project's own test, lint, and build
commands at runtime instead of assuming a toolchain.

```
Coder ─► Orchestrator ─► Reviewer ─► Orchestrator ─► Executive Reviewer ─► Orchestrator ─► Converged
        (the orchestrator relays the mailbox files and verdict lines verbatim — agents never talk to each other)
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

The skill does **not** pin models. At startup the orchestrator asks you to choose a model and a
reasoning effort for **each** role (Coder, Reviewer, Executive Reviewer), and whether to remember
that choice in your user profile (every future session) or only for the current session. Choices
saved to the user profile are reused automatically on later runs.

| Runtime | Recommended Coder + Reviewer (inner) | Recommended Executive Reviewer (outer) |
| :--- | :--- | :--- |
| **GitHub Copilot CLI** | `gemini-3.7-flash` — effort `medium` | `claude-opus-5` — effort `high` |
| **Claude Code** | `claude-opus-5` — thinking `low` | `claude-opus-5` — thinking `high` |

These are only recommendations: they pre-fill the question and act as the fallback when you
decline to choose. If a model is unavailable in the runtime, the orchestrator falls back down a
generic tier list (`gemini-3.6-flash` → `gpt-5.4-mini` → `claude-haiku-4.5` for the inner loop;
`claude-opus-4.8` → `gpt-5.6-sol` → `claude-sonnet-5` for the executive) and, as a last resort,
omits the field entirely. Whatever actually ran is disclosed in the final report.

## Usage

Once installed, trigger it by intent or by name:

- "run the agentic loop on the auth refactor"
- "start agents and make them talk"
- "/swe-agentic-loop"

The orchestrator will:

1. Detect the host runtime and your repository's toolchain and test commands.
2. Ask which model and reasoning effort to use for each role, and where to remember the choice
   (your user profile vs this session only).
3. Ask once whether tests should run in the loop, or be skipped for speed.
4. Present a **Plan Gate**: a short plan plus the task-spec acceptance checklist, and spawn nothing
   until you approve it.
5. Probe the runtime's sub-agent capability, then pick the lifecycle: on a runtime that can keep child
   sessions alive, build the artifact mailbox (outside the repo) with `scripts/bus-init.sh` and spawn
   all three roles **once** up front, each with its declared input path and a single-call wait
   protocol; on a one-shot runtime, fall back to spawning each role in dependency order once its input
   exists. Either way each role gets pointers to the files it must read and write, and no agent IDs are
   exchanged — agents never talk to each other.
6. Iterate: Coder implements → Reviewer audits the `git diff`, runs targeted tests, and ticks the
   task-spec checklist boxes only on evidence.
7. On inner approval, hand the diff to the Executive Reviewer for an architecture/security audit and
   a check that no checklist box is left unticked.
8. Route any executive findings back to the Coder and re-enter the inner loop.
9. Print a final summary showing the full checklist (every box ticked) with the audit trail once
   both tiers approve.

Throughout, the orchestrator **only orchestrates**: it is the single message bus, spawning the
agents, handing each one pointers into the mailbox, and relaying every message verbatim (no
paraphrasing, no softening, no dropped defect lines) while reporting each exchange to the chat as it
happens, attributed to the agent that raised it. It never re-transmits accumulated context, and it is
the single point of failure for message fidelity. It never reviews, edits, or verifies the code
itself; all implementation belongs to the Coder and all judgement to the two Reviewers.

## Support scripts

The skill ships five generic scripts under `skills/swe-agentic-loop/scripts/` (bash/python3 only, no
host paths or project names, `--help` on each). They exist to keep the loop cheap: the expensive part is
the number of turns, so **the orchestrator measures once and hands the agent a small results file; the
agent judges, it does not measure.**

| Script | Purpose |
| :--- | :--- |
| `bus-init.sh` | create the run-scoped mailbox (idempotent); write the task spec + checklist once |
| `bus-verify.sh` | artifact integrity — exists / non-empty / sha256; non-zero on a missing or empty artifact |
| `artifact-slice.py` | diffstat + only the wanted hunks under a byte cap, for the Tier B delivery |
| `verify-checks.py` | one compact pre-submission bundle: CR counts, ```json parse, changed files, forbidden strings, checklist state, `git diff --check` |
| `checklist.py` | render/tick/validate the checklist; a box ticks only with evidence, `--require-all` fails while any box is unticked |

`install.sh` copies `scripts/` along with `SKILL.md`, and the manual `cp -R` copies it too.

## Requirements

- An agent runtime that can spawn a sub-agent and return its result (`task` or equivalent).
  Direct agent-to-agent messaging tools are **not** required; the mailbox is a file-based transport
  that needs no agent-to-agent channel, so if the runtime offers such tools they are optional sugar
  only. The loop also runs where nested spawning is unavailable, with the main chat agent acting as
  the orchestrator.
- A `git` repository (diff-based review degrades gracefully without one).

## Safety controls

- Inner loop capped at 10 iterations; outer loop capped at 10 cycles; 3 full outer resets max.
- Working directory is checked before starting; stashing requires your confirmation.
- Test failures are blocking defects.
- Convergence requires the task-spec acceptance checklist to be fully ticked; the Reviewer ticks a
  box only on evidence, and an unticked box blocks convergence.
- Secrets detected in a diff cause an immediate rejection and are surfaced to you.
- No new test framework is ever installed to satisfy the loop.

## License

MIT — see [LICENSE](LICENSE).
