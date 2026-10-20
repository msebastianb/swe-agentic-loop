---
name: swe-agentic-loop
description: >-
  Execute an optimized, state-of-the-art multi-agent development loop (Coder + Reviewer +
  Executive Reviewer) for any software engineering task in any codebase. Use when the user
  says "agentic loop", "agent loop", "start agents and make them talk", "communication
  between agents", "run agentic loop", "start multi-agent loop", or invokes
  /swe-agentic-loop. Coordinates sub-agents iteratively writing code, reviewing changes,
  running tests (optional), and refining until convergence.
---

# SWE Agentic Loop (Two-Tier Multi-Agent Code & Review)

This skill executes an autonomous multi-agent development loop combining an **Inner Iteration Loop** (fast Coder + Reviewer) and an **Outer Executive Review Loop** (deep Executive Reviewer), orchestrated by a single **Orchestrator** — the main chat agent by default. All inter-agent
traffic flows through one **Message Bus** (Orchestrator <-> agent): the Coder, Reviewer, and
Executive Reviewer never contact each other directly; inter-agent information lives in an
**artifact mailbox** and each spawn carries pointers to it. **Before spawning anything, the Orchestrator asks the user which model and which reasoning effort to use for each role and whether to remember that choice in the current agent's user profile (every future session) or only for the current session, then presents a Plan Gate — the plan plus the task-spec acceptance checklist — and spawns nothing until the user approves it.**

It is **stack-agnostic**: the Orchestrator detects the project's own build/test/lint commands at runtime instead of assuming any particular toolchain.

---

## Orchestrator Role Boundary (Strict)

The main chat agent acts **only** as the Orchestrator. Its job is to spawn, route, poll, and
report — never to do the work itself.

**The Orchestrator MUST NOT:**
- Review, audit, or critique code. Reviewing belongs to `reviewer-agent` (Tier A) and
  `executive-reviewer-agent` (Tier B). Never add your own verdict, opinion, or
  "I also noticed…" findings on top of theirs.
- Write, edit, or fix code, tests, or config. All edits belong to `coder-agent`. If something is
  wrong, route it to `coder-agent` instead of fixing it yourself.
- Run the project's build, test, or lint commands in order to judge the change. The only shell
  the Orchestrator runs is to capture the diff surface for routing
  (`git add -N . && git --no-pager diff HEAD`, `git status --porcelain`).
- Inspect the codebase with file-read or search tools to form an independent opinion.
- Silently rewrite, summarise away, soften, or editorialise a sub-agent's verdict. Relay it.
- Decide the outcome. Convergence is determined solely by the two reviewers' verdicts.

**The Orchestrator MUST:**
- Detect the runtime and the project's own commands (Step 0), run the Plan Gate and obtain the
  user's approval (Step 2), then spawn the sub-agents per the Spawn Protocol (declared input path +
  wait protocol; the on-demand/dependency-order spawn is selected only by the capability probe on a
  one-shot runtime).
- Carry every inter-agent message on the single Orchestrator <-> agent channel, via the artifact
  mailbox, and hand each agent **pointers** to the files it must read and write (see **Message Bus**).
- Relay messages between agents verbatim (verdicts, defect lists, executive findings).
- Poll for sub-agent output and parse for verdict tokens.
- Enforce the iteration caps and timeouts.
- **Report every exchange to the chat as it happens** (see below).
- Produce the Final Report at convergence.

> If the Orchestrator is ever tempted to fix, review, or verify something itself, that is the
> signal to delegate it to the appropriate sub-agent instead.

---

## Message Bus (Single Channel + Artifact Mailbox)

**All inter-agent communication flows through exactly one channel: the Orchestrator.** There is no
second channel and no side channel. The architecture is Orchestrator <-> agent, never agent <-> agent.

Rules:
- **Agents never call a peer.** No agent sends to, reads from, or addresses another agent.
  `coder-agent`, `reviewer-agent`, and `executive-reviewer-agent` know only the Orchestrator.
- **The Orchestrator is the only carrier of inter-agent information.** It is the single point of
  failure for message fidelity.
- **No agent receives a peer's agent id.** Agents are never handed `<CODER_AGENT_ID>`,
  `<REVIEWER_AGENT_ID>`, or `<EXECUTIVE_REVIEWER_AGENT_ID>`, and never look one up. Peer discovery
  (`list_agents`), ID back-binding, and sibling enumeration are deliberately absent from this skill.
- **Peer-to-peer tools are not required.** The protocol never relies on `write_agent`, `read_agent`,
  or `list_agents`. If a runtime happens to expose such channels, they are optional sugar only — the
  loop must work without them.

### The artifact mailbox (pointers, not payloads)

Inter-agent information is **not** re-transmitted inside prompts. It lives in an **artifact mailbox**:
a scratch directory the Orchestrator owns, kept **outside the reviewed repository** (for example under
the OS temp/cache directory — never inside the repo, so it never pollutes `git status` or the diff).
The Orchestrator tells each agent **which file to read and which file to write**.

- The **task specification is written to the mailbox once** and is never repeated in a spawn prompt.
  It carries the specification, the testing strategy, the project commands, and the **acceptance
  checklist** that defines done (see below).
- Each spawn carries **only pointers**: the role, the task-spec file path, the path of the single
  previous message it must act on, and the path where it writes its own output.
- Anything an agent can read for itself is **not sent**: the Tier A reviewer captures the diff itself
  with `git`; the Executive Reviewer reads the diff artifact the Orchestrator points it at; no agent is
  ever handed the accumulated conversation or the whole history.
- The mailbox is **ephemeral**: it is scratch state for this run, it is **never committed**, and
  cleaning it up at the end of the run is the Orchestrator's job.

### The task-spec checklist (definition of done)

The task spec the Orchestrator writes to the bus carries a markdown **checklist**, one box per
acceptance criterion:

```
- [ ] <verifiable criterion>
- [ ] <verifiable criterion>
```

- The checklist **is** the definition of done. A criterion that cannot be verified is not a valid
  box: rewrite it in observable form (a diff hunk, a count, a command output, a test assertion)
  before the plan is approved.
- **A box is ticked only on evidence**: a diff hunk, the real output of a command, or a
  `[FILE:LINE]` reference. Never tick a box on the strength of a claim by whoever did the work.
- **Who produces does not tick**: the Coder can never tick its own boxes. The Reviewer ticks them in
  its verdict, or the Orchestrator ticks them on the basis of the Reviewer's verdict.
- A box ticked without evidence is **un-ticked by the Reviewer**, citing the box.
- The checklist lives in the **bus file** (the task spec), updated by the Orchestrator as verdicts
  arrive, so its state is readable by another turn or another runtime. The bus stays outside the
  repo: ephemeral and never committed (pointers-not-payloads, as approved).
- `scripts/checklist.py` renders, ticks and validates it: a box is ticked **only** with evidence
  (ticking without evidence is refused), and `validate --require-all` exits non-zero while any box is
  unticked. The Orchestrator runs `scripts/verify-checks.py` once before a submission and cites the
  KB-scale bundle as the evidence, so the Reviewer judges rather than measures (see **Cost rule**).

The checklist is a **condition of convergence**: the Reviewer's verdict states which boxes are
satisfied (with `[FILE:LINE]` or command output) and which are not; a required box that is not
satisfied makes the verdict `VERDICT: REJECTED` with that box listed among the defects; the Executive
Reviewer (Tier B) verifies that **no box remains unticked** before approving; and convergence may be
declared only when every box is ticked. If a box is genuinely unreachable the loop does **not**
converge — it escalates to the user, naming the box and why. The Final Report shows the full checklist
with every box `[x]` and its evidence.

### Cost rule (a requirement, not advice)

**Relay pointers and verdict lines — never re-transmit accumulated context.** The Orchestrator must
not duplicate to an agent what is already on disk; it passes a path, not a payload. A spawn prompt
stays small (role plus a few file paths) no matter how large the task, the diff, or the history grows.

### The mailbox needs no agent-to-agent channel

This transport works on a runtime that offers nothing but spawn-and-result: the mailbox is ordinary
files and the Orchestrator alone reads and writes the pointers. It requires no `write_agent` /
`read_agent` / `list_agents` capability, and no agent-to-agent channel of any kind.

### Stateless spawns

Every spawn is independent and may be a one-shot process that remembers nothing from a previous turn.
The protocol must not depend on agent memory or on a live session. Because the shared state lives in
the mailbox, a stateless spawn carries everything it needs as **file pointers**, not as inline payload:

1. the **task-spec file** (written once, containing the specification, the acceptance checklist, the
   testing strategy, and the project commands);
2. the **single previous message's file path** — the peer output it must act on (the Coder's
   submission for the Reviewer; the Reviewer's or Executive's verdict for the Coder);
3. its **own output file path**, where it writes the message the next agent will read.

Re-spawning a role is always a fresh, fully-specified spawn, never a resume of an old conversation.

### Mailbox integrity (lost or empty artifacts)

Because the bus carries pointers rather than payloads, a missing or empty output file is the most
likely silent break. Before relaying any agent's result, the Orchestrator **verifies that the output
file it was told to expect exists and is non-empty**:

- On a miss (missing, empty, or truncated file), it **re-spawns that role once** with the same
  fully-specified pointers, inside the existing two-re-spawns-per-role budget (Step 6).
- On a recurrence for the same role, it **escalates to the user** with the mailbox path and the role,
  rather than looping.
- The mailbox directory is created **run-scoped and unique** (a fresh `mktemp -d`-style directory
  under the OS temp/cache root) so concurrent runs cannot collide or clear each other's artifacts.

### Two possible orchestrator placements

The protocol runs identically under either placement. Choose by capability, and never assume nested
spawning:

| Placement | When to use | Notes |
| :--- | :--- | :--- |
| **(a) Main chat agent as Orchestrator** | **Default and portable.** Use whenever in doubt. | Works even where a sub-agent cannot spawn sub-agents. This is the architecture the protocol is written around. |
| **(b) Dedicated orchestrator sub-agent** | **Conditional only.** Use only where the runtime allows a sub-agent to spawn sub-agents (nested spawning). | The orchestrator sub-agent spawns the Coder, Reviewer, and Executive Reviewer and relays between them. If nested spawning is unavailable, this placement is not possible. |

Some runtimes forbid nested spawning; on those, placement (a) is the only possibility.

### Acceptance criterion

On a runtime that provides **nothing but "spawn an agent and get its result"**, the loop must work
**unchanged** — the mailbox is a file-based transport that needs no agent-to-agent channel, no degraded
mode, and no optional tool that turns out to be required. Every pointer an agent needs arrives in its
spawn prompt; every result comes back to the Orchestrator by the ordinary return of the spawn. Direct
agent-to-agent channels, where they exist, are a convenience the protocol may exploit but never
depends on.

### Support scripts (measure once, judge once)

The mailbox, its integrity, the diff delivered to Tier B, the pre-submission checks, and the checklist
are all deterministic, so they ship as five generic scripts under `scripts/` (bash/python3 only, no
host paths, no project names, `--help` on each). Use them to keep the loop cheap:

- `scripts/bus-init.sh` — **mailbox setup**: creates the run-scoped bus with `mktemp -d`, writes the
  task spec and checklist once, and prints the paths. Idempotent: re-running on the same run reuses it
  and never loses state.
- `scripts/bus-verify.sh` — **artifact integrity**: exists? non-empty? sha256? Exits **non-zero** when
  an artifact is missing or empty, so the mailbox-integrity rule (see above) is executable, not
  discretionary.
- `scripts/artifact-slice.py` — **Tier B delivery**: from a diff, prints the diffstat plus only the
  hunks touching the requested paths, under a configurable **byte cap** — so the executive is never
  sent a whole 78 KB diff.
- `scripts/verify-checks.py` — **pre-submission verification**: one compact (~KB) bundle with the
  CR/CRLF counts per file, the parse of every ```json block, the modified-file list, a forbidden-string
  scan, the checklist state, and `git diff --check`.
- `scripts/checklist.py` — **checklist as definition of done, made executable**: render/tick/validate;
  a box is ticked **only** with evidence (ticking without evidence is refused), and `--require-all`
  exits non-zero while any box is unticked.

**Cost rule (a requirement, not advice):** the expensive part of a review is the *number of turns*, not
the message size — every turn re-sends the accumulated context. So the **Orchestrator measures once and
hands each agent a small results file; the agent judges, it does not measure.** The Orchestrator runs
these deterministic checks one time and points the agent at the KB-scale output instead of having the
agent spend turns re-deriving them.

---

## Agent Lifecycle (Spawn Once, Wait on the Bus)

**Default: spawn each role once at the start of the loop and keep it alive until convergence.** After
the Plan Gate approves and the mailbox exists (see **Message Bus**), the Orchestrator spawns all three
roles — `coder-agent`, `reviewer-agent`, `executive-reviewer-agent` — up front and **never re-spawns
them per turn or per submission**. Each role is given its **declared input path** (which may not exist
yet — it is *declared*, not *absent*) and a **wait protocol** that wakes it when its artifact appears.

This is the default **only when the runtime keeps child sessions alive and can wake them**. On a
runtime where every spawn is one-shot, the loop degrades to **spawn-on-demand in dependency order**
(the previously approved model) — and which of the two applies is decided by a **capability probe**,
never assumed.

### Capability probe (decide the lifecycle, don't assume it)

Before spawning, the Orchestrator establishes whether the runtime can **keep a child alive and wake it**:

1. **Spawn a trivial probe agent** with a prompt that asks it to write a sentinel to a mailbox file,
   then wait — or inspect the runtime's documented sub-agent semantics directly.
2. If the runtime **returns a live handle** that can be awaited again (a session the parent can resume
   or signal), or explicitly documents persistent child sessions, the runtime **supports** the spawn-once
   lifecycle: use it.
3. If the runtime offers **only spawn-and-result** (the child runs to completion and returns, nothing to
   wake), the runtime is **one-shot**: fall back to **spawn-on-demand per dependency** (Step 3's
   fallback), the model approved in the previous cycle.
4. Record the probe's outcome (which lifecycle was chosen and why) and state it in the final report.
   **Never assume** the runtime can hold a child alive; if the probe is inconclusive, treat the runtime
   as one-shot.

### Wait protocol (one blocking call, never a poll loop)

An idle role waits with **a single blocking call**, not a turn-consuming poll:

- **One call, bounded**: `sleep <interval>` then read the declared input path and check for the
  **end-of-file marker** the producer writes as its last line (a sentinel such as `<<END>>`, or a
  `bus-verify.sh` success). Repeat inside that one call only until the artifact is complete.
- **Declared maximum wait**: the wait has a stated ceiling (the loop timeout, **180 s** per the Timeout
  & Wait Handling rules). On reaching it, the role returns "still waiting" rather than blocking forever.
- **Explicit ban**: a role **must not** loop over "check the file → return to the model → check again",
  because every such cycle consumes an API turn and re-sends context. Idle wait cost must be ~0: the
  waiting happens inside the blocking call, not across turns.

### Reuse rule (1 spawn per role per loop)

- **1 spawn per role per loop**, plus crash re-spawns. The fixed spawn cost is therefore paid **once per
  role per loop**, not once per turn.
- **No re-spawn when nothing changed** since the previous verdict (the role's input is byte-identical to
  what it already read): route the message to the live role instead of re-spawning it.
- **Re-spawn is allowed only for**: (a) a **crash/failure** of the child — budget **2 per role**, then
  escalate (Step 6); or (b) a **one-shot runtime**, where each turn is necessarily a fresh spawn.

### F1 reconciled (declared input + wait, not "spawn only when input exists")

The earlier rule "spawn a role only once its input artifact exists" is superseded for live runtimes by
**"spawn with a declared input path + wait protocol"**: the path is named at spawn time even if the file
does not exist yet, and the role waits on it. There is **no "Reviewers First"** ordering and **no spawn
of a role whose input is undeclared**. The on-demand fallback (spawn in dependency order, each role only
when its input exists) remains documented and is selected by the probe.

> In both lifecycles the constraints are unchanged: a single Orchestrator <-> agent channel, no peer
> tools or peer IDs, stateless spawns, verbatim relay, pointers-not-payloads, the checklist as
> definition of done, per-role model/effort tokens, and the caps **10 / 10 / 3** with the **180 s**
> timeout untouched.

---

## Live Reporting Protocol (Chat Visibility)

The user must be able to follow the loop in real time without reading the sub-agent transcripts.
The Orchestrator posts a short chat update at **every** state transition and **every** message
exchange. Never run the loop silently.

### When to Post an Update

| Event | Report |
|---|---|
| Runtime & commands detected | Which runtime, and the build/test/lint commands discovered |
| Sub-agents spawned | Which agents and which models |
| Testing strategy resolved | Which strategy, and whether it was reused from history or asked |
| Coder submission relayed | That the Orchestrator is carrying the Coder's submission to the Reviewer, plus the files the Coder touched |
| Reviewer verdict received | `APPROVED` / `REJECTED` plus the defect list, quoted |
| Defects routed back to Coder | Confirmation of the hand-off and the current inner iteration count |
| Inner loop approved | That Tier A converged, and that Tier B is being invoked |
| Diff handed to Executive Reviewer | The diff stat being sent (files and changed lines) |
| Executive verdict received | `APPROVED` / `REJECTED` plus the findings, quoted |
| Executive findings routed back | Confirmation of the hand-off and the reset of the inner counter |
| Cap or timeout hit | Which cap, and the state the loop stopped in |
| Sub-agent crash / re-spawn | Which agent failed, and that it was re-spawned |
| Convergence | Hand off to the Final Report |

### Update Format

Keep each update to a few lines. Attribute every statement to the agent that produced it — the
Orchestrator never speaks in its own voice about code quality.

```
**[Inner Loop - iteration 2/10]**
`coder-agent` -> Orchestrator -> `reviewer-agent`: applied edits to `src/services/payment.ts`
`reviewer-agent` -> Orchestrator -> `coder-agent`: **VERDICT: REJECTED**
> 1. [src/services/payment.ts:88] Missing null check on the resolved amount.
> 2. [src/services/payment.ts:140] Duplicated helper - reuse `resolveAmount`.
Routing the defects back to `coder-agent`.
```

```
**[Outer Loop - cycle 1/10]**
Tier A approved. Sending the diff (3 files, +84 / -12) to `executive-reviewer-agent`.
```

### Reporting Rules
- **Quote, don't paraphrase.** Verdicts and defect lists are relayed as written by the reviewer,
  in a blockquote. Trim only for length, never for meaning.
- **Always attribute.** Every finding is prefixed with the agent that raised it.
- **No independent commentary.** Do not agree, disagree, or add findings of your own.
- **Report rejections in full.** A rejection is the most useful signal for the user; never
  compress it to "the reviewer found some issues".
- **Report while waiting.** If a poll returns with the agent still running, say so rather than
  going quiet across long stretches.

---

## Workflow Architecture

```
                                  ┌───────────────────────────┐
                                  │   Step 1: User Preference │
                                  │   (ask_user / history)    │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │ Step 2: Plan Gate         │
                                  │ Approve plan + checklist  │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │ Step 3: Spawn Lifecycle   │
                                  │ Probe -> spawn-once, or   │
                                  │ on-demand fallback        │
                                  │ Caps 10/10/3 kept         │
                                  │ Mailbox: pointers only    │
                                  └─────────────┬─────────────┘
                                                │
 ┌──────────────────────────────────────────────┴──────────────────────────────────────────────┐
 │ INNER ITERATION LOOP (model & effort chosen per role)                                        │
 │                                                                                             │
 │  ┌───────────────────────┐   Orchestrator: Submit Diff    ┌──────────────────────────────┐  │
 │  │ Coder Agent           ├───────────────────────────────►│ Reviewer Agent               │  │
 │  │ (`coder-agent`)       │                                │ (`reviewer-agent`)           │  │
 │  │ Model: user-set       │◄───────────────────────────────┤ Model: user-set              │  │
 │  │ Effort: per role      │                                │ Effort: per role             │  │
 │  │ - Implements edits    │   Orchestrator: Defect Feedback│ - Audits git diff & tests    │  │
 │  └───────────────────────┘                                └──────────────┬───────────────┘  │
 │                                                                          │                  │
 │                                                        Inner Approved?   │ (VERDICT:        │
 └──────────────────────────────────────────────────────────────────────────┼─  APPROVED)      │
                                                                            │                  │
                                                                            ▼                  │
                                                          ┌─────────────────────────────────┐  │
                                                          │ Main Orchestrator Agent         │  │
                                                          │ - Reads Inner Reviewer status   │  │
                                                          │ - Enforces Max Iteration Caps   │  │
                                                          └─────────────────┬───────────────┘  │
                                                                            │                  │
                                                 Orchestrator: Submit Diff  │                  │
                                                                            ▼                  │
 ┌─────────────────────────────────────────────────────────────────────────────────────────────┘
 │ OUTER EXECUTIVE REVIEW LOOP (model & effort chosen per role)
 │
 │  ┌─────────────────────────────────────────┐
 │  │ Executive Reviewer Agent                │
 │  │ (`executive-reviewer-agent`)            │
 │  │ Model: user-set                         │
 │  │ Effort: per role                        │
 │  │ - Deep Architectural & Security Audit   │
 │  └────────────────────┬────────────────────┘
 │                       │
 │      Executive Verdict│
 │      ┌────────────────┴────────────────┐
 │      │                                 │
 │  APPROVED                            REJECTED (Defect Feedback)
 │      │                                 │
 │      ▼                                 ▼
 │┌───────────┐                ┌──────────────────────────────────────┐
 ││ Converged │                │ Main Orchestrator routes executive   │
 ││ Final     │                │ feedback to Coder Agent              │
 ││ Report    │                │ Orchestrator: Coder feedback         │
 │└───────────┘                └──────────────────┬───────────────────┘
 │                                                │
 │                                                └───────────► Re-enter Inner Loop
 └───────────────────────────────────────────────────────────────────────────────────────────────
```

> The arrows above denote the logical hand-off of information, not direct agent-to-agent calls.
> Every hand-off is carried by the Orchestrator on the single message bus, which hands each agent a
> pointer to the artifact mailbox file it must read or write (see **Message Bus**); the Coder,
> Reviewer, and Executive Reviewer never contact each other directly.

---

## Model & Effort Selection (Ask the User at Runtime)

**No model or effort is pinned by this skill.** Models and reasoning effort are chosen by the user
at runtime, **per role**, and the Orchestrator MUST ask before spawning anything. The runtime
matrices below are **recommendations only** — they pre-fill the question and act as the fallback
when the user will not choose; they are not mandatory assignments.

**Step A — Detect the host runtime.** Inspect the available sub-agent tooling and model enum:

| Signal | Runtime |
| :--- | :--- |
| `task` tool exposes a `model` enum containing `gemini-*` entries | **GitHub Copilot CLI** |
| `Task` tool with `subagent_type`, no `gemini-*` models available, Anthropic-only model list | **Claude Code** |
| Neither pattern matches | **Unknown** — use the Generic Fallback row |

**Step B — Ask the user, per role.** For **each** role (`coder-agent`, `reviewer-agent`,
`executive-reviewer-agent`), ask which model and which reasoning effort to use, pre-filling each
answer with the recommendation for the detected runtime. If the runtime has no interactive prompt
tool, present the same three questions as plain text and wait for the answers.

```json
{
  "question": "Choose a model and a reasoning effort for each role before I spawn the agents.",
  "roles": [
    { "role": "coder-agent", "model": "<recommended inner model>", "reasoning_effort": "<recommended inner effort>" },
    { "role": "reviewer-agent", "model": "<recommended inner model>", "reasoning_effort": "<recommended inner effort>" },
    { "role": "executive-reviewer-agent", "model": "<recommended outer model>", "reasoning_effort": "<recommended outer effort>" }
  ]
}
```

**Step C — Ask where to remember the choice.** Ask whether the per-role model/effort map should be
saved to the **user profile on the current agent** (applies to every future session) or kept for
the **current session only** (nothing written to disk).

```json
{
  "question": "Where should I remember these model and effort choices?",
  "choices": [
    "Save to my user profile (reuse in every future session)",
    "This session only (write nothing to disk)"
  ]
}
```

**Step D — Apply and persist.**
- **User profile**: write the per-role model/effort map to the current agent's user profile so every
  future session reuses it; skip the question when the profile already holds a map, unless the user
  asks to change it.
- **Session only**: keep the map in memory for this session and write nothing to disk.
- **No choice made**: fall back to the recommended row for the detected runtime (tables below), and
  disclose the fallback in the final report.
- Never abort the loop over model selection; always state the values that actually ran in the final
  report.

### Recommended matrix — GitHub Copilot CLI

| Role | Model | Reasoning Effort |
| :--- | :--- | :--- |
| `coder-agent` (inner) | `gemini-3.7-flash` | `medium` |
| `reviewer-agent` (inner) | `gemini-3.7-flash` | `medium` |
| `executive-reviewer-agent` (outer) | `claude-opus-5` | `high` |

### Recommended matrix — Claude Code

Gemini models are not available, so the recommended inner loop runs on Opus at a deliberately
**low** thinking budget to keep iterations cheap and fast; the recommended outer executive review
keeps the full budget.

| Role | Model | Thinking Effort |
| :--- | :--- | :--- |
| `coder-agent` (inner) | `claude-opus-5` | `low` |
| `reviewer-agent` (inner) | `claude-opus-5` | `low` |
| `executive-reviewer-agent` (outer) | `claude-opus-5` | `high` |

If the runtime does not accept a `reasoning_effort` / thinking parameter on sub-agents, express the
budget in the prompt instead — prefix inner-loop prompts with "Work quickly and do not overthink;
keep reasoning brief." and the executive prompt with "Think deeply and thoroughly before answering."

### Generic Fallback

Used when the user will not choose and the recommended models above are unavailable in the
runtime's model enum, or when a chosen model/effort is rejected. Never invent a model identifier
— if a name is rejected, downgrade one step and continue.

| Role | Fallback Order |
| :--- | :--- |
| `coder-agent` / `reviewer-agent` | Any fast/cheap tier: `gemini-3.6-flash` → `gpt-5.4-mini` → `claude-haiku-4.5` → `gpt-5-mini` → omit `model` |
| `executive-reviewer-agent` | Any strongest reasoning tier: `claude-opus-4.8` → `gpt-5.6-sol` → `claude-sonnet-5` → omit `model` |

If every candidate is rejected, omit the `model` field entirely and let the agent type's default
apply — the loop protocol still functions, only the cost/quality profile changes. State the
substitution in the final report so the user knows which models actually ran.

---

## Orchestrator Execution State Machine

```
   [STATE 0: INIT]                 ────── Detect host runtime + recommended models, repo/VCS state, test commands
          │
          ▼
   [STATE 1: RESOLVE_PREFERENCES]   ────── (Reuse history OR ask_user: per-role model/effort, remember-scope, testing strategy; fallback to plain text)
          │
          ▼
   [STATE 2: PLAN_GATE]            ────── Plan Gate: produce the plan + the task-spec checklist and ask the user to approve
          │                                (no spawn until approved; rewrite and re-ask on edits; stop if the user refuses)
          ▼
   [STATE 3: SPAWN_SUB_AGENTS]     ────── Mailbox built once (scripts/bus-init.sh); capability probe picks
          │                                spawn-once (all three roles up front) or the on-demand fallback
          ▼
 ┌─►[STATE 4: INNER_LOOP_EXECUTION] ────── (Coder edits -> Reviewer audits diff & tests)
 │        │
 │        ├────── (VERDICT: REJECTED & Inner Count < 10) ──► Re-run Coder
 │        │
 │        └────── (VERDICT: APPROVED / native approval phrase)
 │                  │
 │                  ▼
 │         [STATE 5: OUTER_LOOP_EXECUTION] ── (Orchestrator passes diff to executive reviewer)
 │                  │
 │                  ├────── (VERDICT: REJECTED & Outer Count < 10) ──► Route feedback back to Coder
 │                  │                                                 (Reset Inner Count = 0)
 └──────────────────┤
                    └────── (VERDICT: APPROVED / native approval phrase and checklist fully ticked)
                              │
                              ▼
                     [STATE 6: CONVERGED_FINAL_REPORT]
```

---

## Step-by-Step Execution Protocol

### Step 0: Runtime & Project Discovery

Before spawning agents, the Orchestrator MUST resolve three things: **which model and reasoning effort to use, per role, and where to remember that choice** (see the Model & Effort Selection section above — ask the user, pre-filled with the recommendation for the detected runtime), **the project's own conventions**, so sub-agent prompts contain concrete, correct commands, and **the persistence scope** (user profile on the current agent vs current session only):

1. Confirm a VCS root exists (`git rev-parse --show-toplevel`). If the directory is not a git repository, warn the user that diff-based review is degraded and offer to `git init` or proceed with file-listing review only.
2. Detect the toolchain and its test/lint/build commands from the manifests actually present, for example:
   - `package.json` scripts (npm / pnpm / yarn / bun)
   - `pyproject.toml`, `tox.ini`, `pytest.ini` (pytest, uv, poetry)
   - `go.mod` (`go test ./...`, `go vet ./...`)
   - `Cargo.toml` (`cargo test`, `cargo clippy`)
   - `Makefile`, `Justfile`, `build.gradle`, `pom.xml`, `*.csproj`
3. Record the resolved commands as `<INSERT_PROJECT_COMMANDS>` inside the task-spec artifact written to the mailbox (see **Message Bus**), and point every sub-agent at that file instead of repeating them in each prompt.
4. Never invent a command. If no test command can be discovered, set the testing strategy to static review only and say so in the final report.
5. Record the resolved model/effort pair per role as `<CODER_MODEL>` / `<CODER_EFFORT>`, `<REVIEWER_MODEL>` / `<REVIEWER_EFFORT>`, and `<EXECUTIVE_MODEL>` / `<EXECUTIVE_EFFORT>`, persist them to the user profile or keep them session-only as the user chose, and report them in the final summary.

---

### Step 1: User Preference Check (Models, Effort & Testing Strategy)

**BEFORE starting any background sub-agents:**
1. **Resolve Models, Effort & Persistence First**: Run the Model & Effort Selection steps (A–D) to capture the per-role model/effort map and the chosen persistence scope (user profile vs session only).
2. **Check Conversation History**: Search prior turns to see if the user specified a testing preference ("run tests" vs "skip tests / speed").
3. **Reuse Existing Selection**: If explicitly stated or selected earlier, **reuse that choice** directly without prompting again.
4. **Prompt Only If Unset**: Call `ask_user` only if no preference is present in history:

```json
{
  "question": "Should unit/integration tests be run automatically as part of the agentic loop, or skipped for faster iterations?",
  "choices": [
    "Run tests in loop (Recommended - runs targeted tests, catches regressions)",
    "Skip tests for speed (Faster iterations, static code review & linting only)"
  ]
}
```

5. **User Input Fallback**: If the `ask_user` tool is unavailable or unsupported in the runtime environment, fall back to presenting the **same three questions** directly as plain text and waiting for the answers: (a) the per-role model and reasoning effort, (b) where to remember that choice (user profile vs session only), and (c) the testing strategy. Never spawn before all three are resolved.

---

### Step 2: Plan Gate (Mandatory Before Any Spawn)

**After preference resolution (Step 1) and BEFORE the first spawn**, the Orchestrator produces and
submits to the user, in a single prompt:

a) a **short, concrete plan**: the approach, the files/artifacts that will be touched, the order of
   steps, the known risks, and what will NOT be done;
b) the **task spec as a checklist** — the acceptance criteria as markdown checkboxes (see **The
   task-spec checklist** in the Message Bus section).

The Orchestrator then **spawns nothing until the user approves** the plan (or supplies a corrected
version). If the user edits the plan, the plan is rewritten and confirmation is requested again. If
the user declines to plan, the loop **stops** — there is no silent default. The gate is per-run: if
the task changes mid-run (a new user requirement), it requires a **plan amendment** carrying the same
approval, never a silent addition.

---

### Step 3: Initialize Sub-Agents (`task` Tool Invocations & Stateless Spawns)

Sub-agents never communicate directly; the Orchestrator relays everything through the artifact mailbox
(see **Message Bus**). Every spawn is stateless and self-contained — what the agent acts on is the
payload, not a live session or agent memory, and the payload carries **file pointers, not inline context**.

#### Mandatory Spawn Protocol

**The lifecycle is chosen by the capability probe** (see **Agent Lifecycle**): spawn-once by default on a
live-session runtime, on-demand by dependency on a one-shot runtime.

**A. Spawn-once (default when the runtime keeps child sessions alive):**

0. **Mailbox setup (once)**: create the run-scoped, unique bus with `scripts/bus-init.sh` (or a fresh `mktemp -d`-style directory under the OS temp/cache root, never inside the repo) and write the task specification to `<TASK_SPEC_PATH>` once (specification + acceptance checklist + testing strategy + `<INSERT_PROJECT_COMMANDS>`). Decide each role's output-file path.
1. **Spawn all three roles once, up front**, each with its **declared input path** (which may not exist yet) and its own output path: `coder-agent` (`<INPUT_MESSAGE_PATH>` = `NONE`); `reviewer-agent` (the Coder's output path, declared, waiting); `executive-reviewer-agent` (the diff artifact path as `<DIFF_ARTIFACT_PATH>`, declared, waiting). Each waits with the **single blocking wait call** (see **Agent Lifecycle**) and wakes when its artifact is complete.
2. **Route, don't re-spawn**: after each message, hand the next agent its input file and let the live role act. **No re-spawn** while nothing has changed since the previous verdict; re-spawn only on a crash (budget 2 per role) or a one-shot runtime.
3. **Mailbox integrity before every relay**: run `scripts/bus-verify.sh <artifact>` on the file you were told to expect; a non-zero exit is the miss signal (re-spawn once, then escalate).
4. **Tier B diff delivery**: before waking the Executive Reviewer, capture the diff and shrink it with `scripts/artifact-slice.py --diff <DIFF_ARTIFACT_PATH> --path <paths>` so only the relevant hunks under the byte cap are delivered.

**B. Spawn-on-demand fallback (one-shot runtime only — selected by the probe):** spawn each role in dependency order, each only once its input artifact exists — `coder-agent` first, then `reviewer-agent` after each submission, then `executive-reviewer-agent` after Tier A approval. Never spawn a role whose input artifact does not yet exist.

No agent ids are exchanged under either lifecycle: agents never contact each other, so no id is captured or handed on.

---

#### Phase 1: Coder Agent (`coder-agent`)
- **Agent Type**: `general-purpose`
- **Model**: `<CODER_MODEL>` — the value chosen by the user at runtime (recommended default per Model & Effort Selection)
- **Reasoning Effort**: `<CODER_EFFORT>` — the value chosen by the user at runtime
- **Role**: Reads the task-spec and feedback files the Orchestrator points it at, inspects the codebase, applies edits using `edit`/`create`/bash tools while actively avoiding code duplication, and writes its summary for the Orchestrator (never for another agent) so the Orchestrator can carry the submission to the Reviewer.

```json
{
  "name": "coder-agent",
  "agent_type": "general-purpose",
  "mode": "background",
  "model": "<CODER_MODEL>",
  "reasoning_effort": "<CODER_EFFORT>",
  "description": "Implement code changes for task",
  "prompt": "You are the Coder Agent (coder-agent). Your role is to implement the requested code changes in this repository. The Orchestrator points you at files in the artifact mailbox; you never contact another agent directly.\n\nROLE: coder\nTASK SPEC FILE (read this first): <TASK_SPEC_PATH>\nPREVIOUS MESSAGE FILE (read this; the reviewer's or executive's verbatim feedback to act on, or NONE): <INPUT_MESSAGE_PATH>\nYOUR OUTPUT FILE (write your summary and changed-file list here): <OUTPUT_MESSAGE_PATH>\n\n1. Read the task-spec file and any previous-message file carefully.\n2. Inspect relevant files using view, grep, or glob, and follow the conventions already present in this codebase.\n3. CODE DEDUPLICATION & DRY PRINCIPLE: Before writing new logic, search the repository for existing utilities, shared modules, and helpers to avoid repeating code. Reuse existing helpers or extract common reusable functions whenever implementing similar logic across multiple modules.\n4. Make precise, surgical edits using the edit or create tools. Do not refactor unrelated code.\n5. When your edits are applied, write a short summary (files touched + what changed) to your output file and report back to the Orchestrator. The Orchestrator carries your submission to the reviewer; you never message the reviewer yourself.\n6. If the Orchestrator points you at a defect list or executive findings, apply the requested fixes and write your updated summary again.\n7. CHECKLIST: the task spec carries the acceptance checklist. Do not tick its boxes yourself; you produce the evidence (diff, command output) and the Reviewer ticks them. State which criteria you believe you satisfied and how each is verified.\n8. TERMINAL BEHAVIOR: when the Orchestrator relays an APPROVED verdict, make no further edits and end your turn."
}
```

#### Phase 2: Reviewer Agent (`reviewer-agent`)
- **Agent Type**: `code-review`
- **Model**: `<REVIEWER_MODEL>` — the value chosen by the user at runtime (recommended default per Model & Effort Selection)
- **Reasoning Effort**: `<REVIEWER_EFFORT>` — the value chosen by the user at runtime
- **Role**: Reads the task-spec and Coder-message files the Orchestrator points it at, captures the diff itself, audits it for bugs and security risks and code duplication (DRY principle), runs targeted tests, and writes formatted verdicts for the Orchestrator (never for another agent).

```json
{
  "name": "reviewer-agent",
  "agent_type": "code-review",
  "mode": "background",
  "model": "<REVIEWER_MODEL>",
  "reasoning_effort": "<REVIEWER_EFFORT>",
  "description": "Audit git diff, check DRY code duplication, and run tests",
  "prompt": "You are the Reviewer Agent (reviewer-agent). Your role is to perform rigorous code reviews on changes made by Coder Agent. The Orchestrator points you at files in the artifact mailbox; you never contact another agent directly.\n\nROLE: reviewer (Tier A inner review)\nTASK SPEC FILE (read this first): <TASK_SPEC_PATH>\nPREVIOUS MESSAGE FILE (read this; the Coder submission you must act on): <INPUT_MESSAGE_PATH>\nYOUR OUTPUT FILE (write your verdict here): <OUTPUT_MESSAGE_PATH>\n\n1. Read the task-spec file and the previous-message file, then capture the complete diff surface yourself with bash:\n   git add -N . && git --no-pager diff HEAD\n   and verify untracked files with: git status --porcelain\n2. Audit changes against the task requirements, security rules, error handling, the repository's existing lint/style conventions, and DRY principles (ensure code duplication is avoided by reusing existing helpers/shared modules or extracting reusable functions).\n3. If the testing strategy is 'run_tests', execute the narrowest relevant test command from the spec's PROJECT COMMANDS. Never introduce a new test framework.\n4. Judge only the changed surface. Do not demand fixes for pre-existing issues unrelated to the task.\n5. Checklist verdict: for each acceptance-criterion box in the task spec, state whether it is satisfied and the evidence (a diff hunk, real command output, or [FILE:LINE]). Tick a box only on evidence, never on a claim; un-tick any box not backed by evidence and report it. If a required box is not satisfied, the verdict is REJECTED with that box among the defects.\n6. Write your verdict to your output file and return it to the Orchestrator (never message another agent), using one of the following exact token formats:\n   - If defects found: 'VERDICT: REJECTED\\nDefects found:\\n1. [FILE:LINE] Issue description (e.g., duplicated code/missing helper reuse)...\\nPlease fix and resubmit.'\n   - If code is clean, deduplicated, tests pass, and every checklist box is satisfied with evidence: 'VERDICT: APPROVED. All checks pass with zero defects; checklist fully ticked.'"
}
```

#### Phase 3: Executive Reviewer Agent (`executive-reviewer-agent`)
- **Agent Type**: `code-review`
- **Model**: `<EXECUTIVE_MODEL>` — the value chosen by the user at runtime (recommended default per Model & Effort Selection)
- **Reasoning Effort**: `<EXECUTIVE_EFFORT>` — the value chosen by the user at runtime
- **Role**: Performs high-level architectural, structural, security, and DRY code-duplication reviews on the diff the Orchestrator points it at in the artifact mailbox. It never contacts another agent.
- **Strict Role Boundary**: the Executive Reviewer does **NOT** run search or enumeration commands (`grep`, `glob`, `ls`) or navigate the filesystem. It **may read, with a read tool, only the specific artifacts the Orchestrator points it at** (the task-spec file and the captured diff file) — those pointed files are exempt from the inspection ban — and never inspects anything else or the whole conversation.

```json
{
  "name": "executive-reviewer-agent",
  "agent_type": "code-review",
  "mode": "background",
  "model": "<EXECUTIVE_MODEL>",
  "reasoning_effort": "<EXECUTIVE_EFFORT>",
  "description": "Executive architecture, security, and DRY deduplication review of provided diffs",
  "prompt": "You are the Executive Reviewer Agent (executive-reviewer-agent). Your sole role is to perform high-level architectural, structural, security, and code-duplication reviews on code changes approved by the Inner Loop. The Orchestrator points you at files in the artifact mailbox; you never contact another agent directly.\n\nROLE: executive reviewer (Tier B outer review)\nTASK SPEC FILE (read this first): <TASK_SPEC_PATH>\nDIFF ARTIFACT FILE (read this; the diff the Orchestrator captured for you): <DIFF_ARTIFACT_PATH>\nYOUR OUTPUT FILE (write your verdict here): <OUTPUT_MESSAGE_PATH>\n\nSTRICT ROLE BOUNDARIES & PROTOCOL:\n1. You are spawned by the Orchestrator with pointers to the task-spec file and the diff artifact; read them yourself. Do not wait for a live session.\n2. Do NOT run search or enumeration commands (grep, glob, ls) and do not navigate the filesystem. You MAY read the two specific artifacts the Orchestrator points you at — the task-spec file and the diff artifact — with a read tool; those pointed files are exempt from the inspection ban. Evaluate strictly those pointed artifacts and the implementation summary, nothing else.\n3. Evaluate the submitted changes for architectural patterns, modularity, DRY principles (strict avoidance of code duplication and maximum reuse of shared contracts/utils), type safety, security controls, and regression risks.\n4. Verify the task-spec acceptance checklist: every box must be ticked on evidence (a diff hunk, real command output, or [FILE:LINE]); un-tick any box not backed by evidence and report it; if any required box is unsatisfied, reject.\n5. Raise only high-confidence, material findings. Do not raise stylistic nits or request changes outside the task scope.\n6. Write your verdict to your output file and return it to the Orchestrator (never message another agent) in one of two exact token formats:\n   - If the checklist is fully ticked and the audit passes: 'VERDICT: APPROVED. Architectural and security audit passed with zero defects; every checklist box is ticked with evidence.'\n   - If changes required: 'VERDICT: REJECTED\\nExecutive Reviewer Findings:\\n1. [Architectural/Security/Deduplication Issue] Description and recommended fix...'"
}
```

> **Runtime note**: the three JSON templates above use the per-role placeholders `<CODER_MODEL>` /
> `<CODER_EFFORT>` (coder-agent), `<REVIEWER_MODEL>` / `<REVIEWER_EFFORT>` (reviewer-agent), and
> `<EXECUTIVE_MODEL>` / `<EXECUTIVE_EFFORT>` (executive-reviewer-agent), plus the mailbox path
> placeholders `<TASK_SPEC_PATH>`, `<INPUT_MESSAGE_PATH>`, `<OUTPUT_MESSAGE_PATH>`, and
> `<DIFF_ARTIFACT_PATH>`. Substitute the values the user chose (Model & Effort Selection) and the
> concrete mailbox file paths before spawning. If a model or effort field is rejected by the runtime,
> drop that field (see Generic Fallback) rather than aborting the loop.

---

### Step 4: Message Bus & Two-Tier Relay Protocol

Every message travels on the single channel defined in the **Message Bus** section:
agent -> mailbox file -> Orchestrator -> next agent. The Orchestrator relays **verbatim** — it never
paraphrases, softens, or summarises away a defect line, and it is the single point of failure for
message fidelity. Because it hands the next agent the **reviewer's own output file** rather than a copy
it retyped, fidelity is structural: the Orchestrator does not re-embed the message text at all.

Because spawns are stateless, a relay is always a **new spawn whose prompt contains pointers** — the
role, the task-spec path, the one previous-message path, and its own output path — never the
accumulated context. See the **Cost rule** in the Message Bus section.

> **Placeholder convention**: the templates use the per-role values the user chose in the Model &
> Effort Selection step — `<CODER_MODEL>` / `<CODER_EFFORT>`, `<REVIEWER_MODEL>` / `<REVIEWER_EFFORT>`,
> and `<EXECUTIVE_MODEL>` / `<EXECUTIVE_EFFORT>` — plus the mailbox paths `<TASK_SPEC_PATH>`,
> `<INPUT_MESSAGE_PATH>`, `<OUTPUT_MESSAGE_PATH>`, and `<DIFF_ARTIFACT_PATH>`. If the runtime rejects a
> model or effort field, drop that field (see Generic Fallback) rather than aborting the loop.

#### Tier A: Inner Iteration Protocol (Coder -> Orchestrator -> Reviewer, and back)

1. **Coder submission**: `coder-agent` writes its summary (files touched + what changed) to its output
   file, then tells the Orchestrator it is done. It does **not** message the Reviewer.
   - **A submission never carries a verdict.** The Coder reports *what it did* and *which criteria it
     believes it satisfied, with evidence* — nothing more. Verdict tokens (`VERDICT: APPROVED` /
     `VERDICT: REJECTED`) belong **exclusively** to the reviewers: `reviewer-agent` (Tier A) and
     `executive-reviewer-agent` (Tier B). The producer issuing a verdict on its own work is the same
     violation as the producer ticking its own boxes (see the checklist rules): it is judged, never judge.
     The Orchestrator relays a submission as a submission and never rewrites it into a verdict.

2. **Orchestrator points the Reviewer at the files**: it hands `reviewer-agent` the task-spec path, the
   Coder's output file as its `<INPUT_MESSAGE_PATH>`, and its output path (on a live runtime the same
   role is reused; on a one-shot runtime it is re-spawned). Before relaying, the Orchestrator runs the
   deterministic checks **once** — `scripts/bus-verify.sh <coder-output>` for integrity and
   `scripts/verify-checks.py --repo . --checklist <CHECKLIST> --out <CHECKS_PATH>` — and passes
   `<CHECKS_PATH>` so the Reviewer **judges** that KB-scale bundle instead of spending turns measuring.
   The Reviewer still captures the diff itself with `git` — the diff is never sent:
   ```bash
   git add -N . && git --no-pager diff HEAD && git status --porcelain
   ```

3. **Reviewer verdict**: the Reviewer writes its verdict to its output file and returns it to the
   Orchestrator using one of the exact token formats:
   - Defects found:
     ```
     VERDICT: REJECTED
     Defects found:
     1. [src/services/user.ts:42] Missing null check on request payload.
     2. [src/controllers/auth.ts:15] Unhandled promise rejection.
     Please fix and resubmit.
     ```
   - Clean:
     ```
     VERDICT: APPROVED. All checks and tests passed cleanly with zero defects.
     ```

4. **Orchestrator parses and relays**:
   - **Verdict token recognition**: parse for explicit tokens (`VERDICT: APPROVED`, `VERDICT: REJECTED`)
     as well as native natural-language approval phrases (e.g. "no significant issues found",
     "looks good to merge", "all checks pass").
   - **Report to Chat (mandatory)**: immediately post the verdict to the chat, attributed to
     `reviewer-agent` and quoting the verdict and defect lines **verbatim** (from the output file).
     Include the current inner iteration count. Do not add commentary of your own.
   - **Route to the Coder**: if rejected, spawn (or re-specify) `coder-agent` pointing at the Reviewer's
     output file as its `<INPUT_MESSAGE_PATH>` (plus the task-spec path and a new output path). The
     Orchestrator passes the file, so the defect list reaches the Coder **unchanged**. Do not act on the
     defects yourself.
   - **Update the checklist**: record, from the Reviewer's verdict, which boxes are ticked and their evidence in the task-spec file; the Reviewer's evidence, not a claim, is what ticks a box.
   - **Route onward**: if approved, hand the diff to Tier B.

#### Tier B: Outer Executive Review Protocol

Once `reviewer-agent` returns `VERDICT: APPROVED` (or a native approval phrase):

1. **Orchestrator captures the diff to the mailbox and points the Executive Reviewer at it**: write the
   complete diff surface to `<DIFF_ARTIFACT_PATH>` once
   (`git add -N . && git --no-pager diff HEAD > <DIFF_ARTIFACT_PATH>`), then spawn
   `executive-reviewer-agent` with the task-spec path, that diff artifact path, and its own output path.
   The diff is passed as a file, not inlined in the prompt.
   - **Large diff handling**: run `scripts/artifact-slice.py --diff <DIFF_ARTIFACT_PATH> --path <paths>
     --max-bytes <N>` and point the Executive Reviewer at the sliced artifact, so it receives the
     diffstat plus only the relevant hunks under the byte cap rather than a whole 78 KB diff.

2. **Orchestrator evaluation of the executive verdict**: the Executive Reviewer writes its verdict to
   its output file and returns it to the Orchestrator (same tokens / native phrases). The Orchestrator
   does not evaluate, endorse, or dispute the findings — it only relays and routes them.
   - **Report to Chat (mandatory)**: immediately post the executive verdict, attributed to
     `executive-reviewer-agent` and quoting the findings verbatim.

3. **Outcome processing**:
   - **Case B1 — Executive approval** (`VERDICT: APPROVED` or native approval): the outer loop
     converges. Proceed to Step 7 (Final Summary Report).
   - **Case B2 — Executive rejection** (`VERDICT: REJECTED`): spawn (or re-specify) `coder-agent`
     pointing at the Executive Reviewer's output file as its `<INPUT_MESSAGE_PATH>` (plus the task-spec
     path and a new output path), so the findings reach the Coder **verbatim**. Reset the inner loop
     iteration counter to `0` and restart Tier A.

---

### Step 5: Convergence Criteria, Iteration Caps & Timeout Handling

#### 1. Convergence Criteria
The multi-agent loop achieves **Full Convergence** ONLY when all three criteria are met:
1. `reviewer-agent` (the user-selected inner model) issues `VERDICT: APPROVED` (or a native approval phrase) in Tier A.
2. `executive-reviewer-agent` (the user-selected executive model) issues `VERDICT: APPROVED` (or a native approval phrase) in Tier B.
3. The task-spec acceptance checklist is **fully ticked**, every box backed by evidence. If a box is unreachable the loop does **not** converge and escalates to the user.

#### 2. Max Iteration Caps
To prevent infinite communication loops and resource exhaustion:
- **Inner Loop Limit**: Maximum **10 iterations** per inner loop cycle between `coder-agent` and `reviewer-agent`.
- **Outer Loop Limit**: Maximum **10 outer review cycles** with `executive-reviewer-agent`.
- **Global Safety Cap**: Maximum **3 full outer resets**. If the same defect class is reported in three consecutive outer cycles, stop and escalate to the user rather than looping.

#### 3. Timeout & Wait Handling
Waiting, timeouts, and caps are measured on the **return of a spawn**, never on polling a live peer session:
- The Orchestrator waits for each spawn to return its result. If the runtime exposes a wait/timeout option on the spawn call (or a background handle to await), use it; otherwise treat the spawn as a synchronous request whose output is its result.
- If a spawned agent has not returned within **180 seconds**, check the spawn handle/status once, then re-spawn the role with the same fully-specified pointers (stateless spawns make this safe).
- If the spawn never returns or is reported failed, log the error state and ask the user whether to retry or proceed manually.

---

### Step 6: Edge Case Resolution & Safety Controls

| Edge Case / Scenario | Action / Fallback Protocol |
| :--- | :--- |
| **Not a git repository** | Warn the user that diff-based review is unavailable. Offer to run `git init` or fall back to reviewing explicitly listed changed files. |
| **Unclean Working Directory** | Before starting the loop, verify `git status --porcelain`. If uncommitted manual changes exist, ask the user before stashing. If approved, run `git stash push -u -m "agentic-loop-<timestamp>"` to preserve untracked and modified files, and report the stash ref so it can be restored. |
| **No test command discovered** | Downgrade the testing strategy to static review only and state this explicitly in the final report. Never install a new test framework to satisfy the loop. |
| **Model rejected by runtime** | If `task` rejects a `model` or `reasoning_effort` value, retry once with the next candidate in the Generic Fallback order, then retry with the field omitted. Never abort the loop over model selection, and always disclose the substitution in the final report. |
| **Conflicting Feedback (Inner vs Outer)** | Executive Reviewer feedback takes precedence over Inner Reviewer preferences. |
| **Test Failures vs Static Review** | Test failures are treated as blocking defects (`VERDICT: REJECTED`). |
| **Non-Blocking Warnings / Nits** | Reviewer may issue `VERDICT: APPROVED with non-blocking suggestions`. The inner loop can proceed to Tier B. |
| **Sub-Agent Crash or Failure** | If a spawn returns a failure or cancelled status, the Orchestrator re-spawns the sub-agent using `task` (maximum 2 re-spawns per role, then escalate to the user). |
| **Artifact lost / empty output file** | Before relaying, the Orchestrator checks that the expected output file exists and is non-empty; on a miss (or if the mailbox was cleared mid-run) it re-spawns that role once within the two-per-role budget, then escalates on recurrence. See **Mailbox integrity**. |
| **Plan not approved** | If the user declines the Plan Gate or does not respond, the loop stops — no spawn, no silent default. |
| **Cap Exceeded Without Convergence** | Pause the loop, present the current diff and unresolved feedback to the user, and ask for manual direction. |
| **Secrets in the diff** | Any reviewer that detects credentials, tokens, or keys in the diff MUST issue `VERDICT: REJECTED` immediately and the Orchestrator must surface this to the user. |

---

### Step 7: Final Report to User

When the loop terminates (via Full Convergence or Cap Exceeded), present a clean, concise summary to the user, including the full acceptance checklist with every box ticked and its evidence. Then delete the ephemeral mailbox directory (see **Message Bus**) — it is scratch state for this run, it is never committed, and removing it is the Orchestrator's job:

```markdown
### 🤖 Multi-Agent Loop Execution Summary

- **Overall Status**: ✅ Fully Approved (Inner Loop + Executive Review)
- **Models Used**: Coder `<CODER_MODEL>` (<CODER_EFFORT>) · Reviewer `<REVIEWER_MODEL>` (<REVIEWER_EFFORT>) · Executive `<EXECUTIVE_MODEL>` (<EXECUTIVE_EFFORT>)
- **Preference Scope**: <REMEMBERED_IN_USER_PROFILE | SESSION_ONLY>
- **Inner Loop Iterations**: 2 cycles (Coder ↔ Reviewer)
- **Outer Executive Review**: 1 cycle
- **Testing Strategy**: Executed targeted unit tests - 100% passing
- **Acceptance Checklist**: every box ticked (definition of done)

#### Acceptance Checklist (all boxes ticked, with evidence):
- [x] <criterion> — evidence: <[FILE:LINE] or command output>
- [x] <criterion> — evidence: <[FILE:LINE] or command output>

#### Key Changes Applied:
1. `src/services/user.service.ts`: Added payload validation & null safety checks.
2. `src/services/user.service.test.ts`: Added unit test coverage for invalid payloads.

#### Audit Trail:
- **Inner Reviewer**: Approved after iteration 2 fix.
- **Executive Reviewer (<EXECUTIVE_MODEL>)**: Approved architectural design & security posture.
```
