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

This skill executes an autonomous multi-agent development loop combining an **Inner Iteration Loop** (fast Coder + Reviewer) and an **Outer Executive Review Loop** (high-capability Executive Reviewer), orchestrated by the main chat agent.

It is **stack-agnostic**: the Orchestrator detects the project's own build/test/lint commands at runtime instead of assuming any particular toolchain.

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
                                  │ Step 2: Spawn Sub-Agents  │
                                  │ Phase 1: Reviewers First  │
                                  │ Phase 2: Coder with ID    │
                                  │ Phase 3: ID Back-Binding  │
                                  └─────────────┬─────────────┘
                                                │
 ┌──────────────────────────────────────────────┴──────────────────────────────────────────────┐
 │ INNER ITERATION LOOP (fast model)                                                           │
 │                                                                                             │
 │  ┌───────────────────────┐   write_agent (Submit Diff)    ┌──────────────────────────────┐  │
 │  │ Coder Agent           ├───────────────────────────────►│ Reviewer Agent               │  │
 │  │ (`coder-agent`)       │                                │ (`reviewer-agent`)           │  │
 │  │ Model: fast tier      │◄───────────────────────────────┤ Model: fast tier             │  │
 │  │ Reasoning: medium     │                                │ Reasoning: medium            │  │
 │  │ - Implements edits    │   write_agent (Defect Feedback)│ - Audits git diff & tests    │  │
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
                                                 write_agent (Submit Diff)  │                  │
                                                                            ▼                  │
 ┌─────────────────────────────────────────────────────────────────────────────────────────────┘
 │ OUTER EXECUTIVE REVIEW LOOP (high-capability model)
 │
 │  ┌─────────────────────────────────────────┐
 │  │ Executive Reviewer Agent                │
 │  │ (`executive-reviewer-agent`)            │
 │  │ Model: high-capability tier             │
 │  │ Reasoning Effort: high                  │
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
 ││ Report    │                │ write_agent(coder-agent, feedback)   │
 │└───────────┘                └──────────────────┬───────────────────┘
 │                                                │
 │                                                └───────────► Re-enter Inner Loop
 └───────────────────────────────────────────────────────────────────────────────────────────────
```

---

## Model Tier Selection

The skill is model-agnostic. The Orchestrator picks the best available models from the runtime's `task` tool enum:

| Role | Tier | Guidance |
| :--- | :--- | :--- |
| `coder-agent` | **Fast** | A cheap, quick model (e.g. a "flash"/"mini" class model). Reasoning effort: `medium`. |
| `reviewer-agent` | **Fast** | Same tier as the Coder so the inner loop stays cheap. Reasoning effort: `medium`. |
| `executive-reviewer-agent` | **High-capability** | The strongest reasoning model available. Reasoning effort: `high`. |

If a named model is unavailable in the current runtime, omit the `model` field and let the agent type default apply.

---

## Orchestrator Execution State Machine

```
   [STATE 0: INIT]                 ────── Detect repo, VCS state, and project test/lint commands
          │
          ▼
   [STATE 1: CHECK_TEST_PREFERENCE] ────── (Reuse history OR ask_user; fallback to plain text)
          │
          ▼
   [STATE 2: SPAWN_SUB_AGENTS]     ────── Phase 1: Launch Reviewers (substitute Task & Test specs)
          │                                Phase 2: Launch Coder (substitute Task & Reviewer ID)
          │                                Phase 3: ID Back-Binding (send Coder ID to Reviewer)
          ▼
 ┌─►[STATE 3: INNER_LOOP_EXECUTION] ────── (Coder edits -> Reviewer audits diff & tests)
 │        │
 │        ├────── (VERDICT: REJECTED & Inner Count < 10) ──► Re-run Coder
 │        │
 │        └────── (VERDICT: APPROVED / native approval phrase)
 │                  │
 │                  ▼
 │         [STATE 4: OUTER_LOOP_EXECUTION] ── (Orchestrator passes diff to Executive Reviewer)
 │                  │
 │                  ├────── (VERDICT: REJECTED & Outer Count < 10) ──► Route feedback back to Coder
 │                  │                                                 (Reset Inner Count = 0)
 └──────────────────┤
                    └────── (VERDICT: APPROVED / native approval phrase)
                              │
                              ▼
                     [STATE 5: CONVERGED_FINAL_REPORT]
```

---

## Step-by-Step Execution Protocol

### Step 0: Project Discovery (Stack Detection)

Before spawning agents, the Orchestrator MUST establish the project's own conventions so sub-agent prompts contain concrete, correct commands:

1. Confirm a VCS root exists (`git rev-parse --show-toplevel`). If the directory is not a git repository, warn the user that diff-based review is degraded and offer to `git init` or proceed with file-listing review only.
2. Detect the toolchain and its test/lint/build commands from the manifests actually present, for example:
   - `package.json` scripts (npm / pnpm / yarn / bun)
   - `pyproject.toml`, `tox.ini`, `pytest.ini` (pytest, uv, poetry)
   - `go.mod` (`go test ./...`, `go vet ./...`)
   - `Cargo.toml` (`cargo test`, `cargo clippy`)
   - `Makefile`, `Justfile`, `build.gradle`, `pom.xml`, `*.csproj`
3. Record the resolved commands as `<INSERT_PROJECT_COMMANDS>` and inject them into every sub-agent prompt.
4. Never invent a command. If no test command can be discovered, set the testing strategy to static review only and say so in the final report.

---

### Step 1: User Preference Check (Testing Strategy)

**BEFORE starting any background sub-agents:**
1. **Check Conversation History**: Search prior turns to see if the user specified a testing preference ("run tests" vs "skip tests / speed").
2. **Reuse Existing Selection**: If explicitly stated or selected earlier, **reuse that choice** directly without prompting again.
3. **Prompt Only If Unset**: Call `ask_user` only if no preference is present in history:

```json
{
  "question": "Should unit/integration tests be run automatically as part of the agentic loop, or skipped for faster iterations?",
  "choices": [
    "Run tests in loop (Recommended - runs targeted tests, catches regressions)",
    "Skip tests for speed (Faster iterations, static code review & linting only)"
  ]
}
```

4. **User Input Fallback**: If the `ask_user` tool is unavailable or unsupported in the runtime environment, fall back to presenting a plain text question directly to the user to gather their testing strategy selection.

---

### Step 2: Initialize Sub-Agents (`task` Tool Invocations & Spawn Order Safety)

To ensure sub-agents can communicate seamlessly, the Orchestrator MUST follow a strict **Three-Phase Spawn Protocol**.

#### Mandatory Spawn Order Protocol:
1. **Phase 1 (Reviewers First - Prompt Substitutions)**:
   - Substitute `<INSERT_TASK_SPECIFICATION>`, `<INSERT_TESTING_STRATEGY>` and `<INSERT_PROJECT_COMMANDS>` into the `reviewer-agent` and `executive-reviewer-agent` prompt templates.
   - Call `task` (with `mode: "background"`) to spawn `reviewer-agent` and `executive-reviewer-agent`. Capture their returned `agent_id`s (e.g., `<REVIEWER_AGENT_ID>` and `<EXECUTIVE_REVIEWER_AGENT_ID>`).
2. **Phase 2 (Coder Second - Prompt Substitutions)**:
   - Substitute `<INSERT_TASK_SPECIFICATION>`, `<INSERT_PROJECT_COMMANDS>` and the captured `<REVIEWER_AGENT_ID>` into the `coder-agent` prompt template.
   - Call `task` to spawn `coder-agent`. Capture its returned `agent_id` (`<CODER_AGENT_ID>`).
3. **Phase 3 (Reviewer ID Back-Binding)**:
   - Immediately after spawning `coder-agent`, the Orchestrator MUST send a message to `reviewer-agent` via `write_agent`:
     ```typescript
     write_agent({
       agent_id: "<REVIEWER_AGENT_ID>",
       message: "Coder Agent launched. ID for verdict routing: <CODER_AGENT_ID>"
     })
     ```
4. **Peer Resolution Fallback**: If an agent needs to discover peer agent IDs dynamically at runtime, it may call `list_agents(scope: "siblings")`.

---

#### Phase 1A: Reviewer Agent (`reviewer-agent`)
- **Agent Type**: `code-review`
- **Model**: fast tier
- **Reasoning Effort**: `medium`
- **Role**: Monitors `git diff`, audits code for bugs and security risks, checks for code duplication (DRY principle), runs targeted tests, and issues formatted verdicts.

```json
{
  "name": "reviewer-agent",
  "agent_type": "code-review",
  "mode": "background",
  "reasoning_effort": "medium",
  "description": "Audit git diff, check DRY code duplication, and run tests",
  "prompt": "You are the Reviewer Agent (reviewer-agent). Your role is to perform rigorous code reviews on changes made by Coder Agent.\n\nTASK SPECIFICATION:\n<INSERT_TASK_SPECIFICATION>\n\nTESTING STRATEGY:\n<INSERT_TESTING_STRATEGY>\n\nPROJECT COMMANDS (detected from this repository - do not invent others):\n<INSERT_PROJECT_COMMANDS>\n\n1. When notified by Coder Agent or Orchestrator, capture the complete diff surface using bash:\n   git add -N . && git --no-pager diff HEAD\n   and verify untracked files with: git status --porcelain\n2. Audit changes against the task requirements, security rules, error handling, the repository's existing lint/style conventions, and DRY principles (ensure code duplication is avoided by reusing existing helpers/shared modules or extracting reusable functions).\n3. If the testing strategy is 'run_tests', execute the narrowest relevant test command from PROJECT COMMANDS. Never introduce a new test framework.\n4. Judge only the changed surface. Do not demand fixes for pre-existing issues unrelated to the task.\n5. Output your verdict prominently using one of the following exact token formats:\n   - If defects found:\n     write_agent(agent_id: '<CODER_AGENT_ID>', message: 'VERDICT: REJECTED\\nDefects found:\\n1. [FILE:LINE] Issue description (e.g., duplicated code/missing helper reuse)...\\nPlease fix and resubmit.')\n   - If code is clean, deduplicated, and tests pass:\n     write_agent(agent_id: '<CODER_AGENT_ID>', message: 'VERDICT: APPROVED. All checks pass with zero defects.')\n6. PEER DISCOVERY & VERDICT ROUTING: Use <CODER_AGENT_ID> provided in the prompt or initial message to route verdicts. If <CODER_AGENT_ID> is missing or unset, call list_agents(scope: 'siblings') to resolve Coder Agent's ID by name."
}
```

#### Phase 1B: Executive Reviewer Agent (`executive-reviewer-agent`)
- **Agent Type**: `code-review`
- **Model**: high-capability tier
- **Reasoning Effort**: `high`
- **Role**: Stands by for Tier B outer-loop requests from the main Orchestrator. Performs high-level architectural, structural, security, and DRY code-duplication reviews strictly on the diff summary and code changes provided to it by the Orchestrator.
- **Strict Role Boundary**: the Executive Reviewer does **NOT** run file inspection tools, grep/glob searches, or filesystem navigation. It evaluates the diff and implementation artifacts supplied directly in the Orchestrator's review request.

```json
{
  "name": "executive-reviewer-agent",
  "agent_type": "code-review",
  "mode": "background",
  "reasoning_effort": "high",
  "description": "Executive architecture, security, and DRY deduplication review of provided diffs",
  "prompt": "You are the Executive Reviewer Agent (executive-reviewer-agent). Your sole role is to perform high-level architectural, structural, security, and code-duplication reviews on code changes approved by the Inner Loop.\n\nTASK SPECIFICATION:\n<INSERT_TASK_SPECIFICATION>\n\nSTRICT ROLE BOUNDARIES & PROTOCOL:\n1. Stand by for review requests sent by the main Orchestrator agent.\n2. Do NOT run file search commands (grep, glob, view, ls). You evaluate strictly the git diff and implementation summary provided to you in the Orchestrator review request.\n3. Evaluate the submitted changes for architectural patterns, modularity, DRY principles (strict avoidance of code duplication and maximum reuse of shared contracts/utils), type safety, security controls, and regression risks.\n4. Raise only high-confidence, material findings. Do not raise stylistic nits or request changes outside the task scope.\n5. Output your final verdict prominently in one of two exact token formats:\n   - If approved: 'VERDICT: APPROVED. Architectural and security audit passed with zero defects.'\n   - If changes required: 'VERDICT: REJECTED\\nExecutive Reviewer Findings:\\n1. [Architectural/Security/Deduplication Issue] Description and recommended fix...'"
}
```

#### Phase 2: Coder Agent (`coder-agent`)
- **Agent Type**: `general-purpose`
- **Model**: fast tier
- **Reasoning Effort**: `medium`
- **Role**: Reads task specifications, inspects the codebase, applies edits using `edit`/`create`/bash tools while actively avoiding code duplication, notifies the Reviewer agent, and pauses upon approval.

```json
{
  "name": "coder-agent",
  "agent_type": "general-purpose",
  "mode": "background",
  "reasoning_effort": "medium",
  "description": "Implement code changes for task",
  "prompt": "You are the Coder Agent (coder-agent). Your role is to implement the requested code changes in this repository.\n\nTASK SPECIFICATION:\n<INSERT_TASK_SPECIFICATION>\n\nPROJECT COMMANDS (detected from this repository - do not invent others):\n<INSERT_PROJECT_COMMANDS>\n\nTARGET REVIEWER AGENT ID:\n<REVIEWER_AGENT_ID>\n\n1. Read the user requirements carefully.\n2. Inspect relevant files using view, grep, or glob, and follow the conventions already present in this codebase.\n3. CODE DEDUPLICATION & DRY PRINCIPLE: Before writing new logic, search the repository for existing utilities, shared modules, and helpers to avoid repeating code. Reuse existing helpers or extract common reusable functions whenever implementing similar logic across multiple modules.\n4. Make precise, surgical edits using the edit or create tools. Do not refactor unrelated code.\n5. Once edits are applied, submit your diff to Reviewer Agent using write_agent:\n   write_agent(agent_id: '<REVIEWER_AGENT_ID>', message: 'I have applied code changes for the task. Please review the git diff and verify.')\n6. Wait for feedback from Reviewer Agent or Orchestrator. When feedback arrives, apply the requested fixes and submit again.\n7. TERMINAL BEHAVIOR: Upon receiving VERDICT: APPROVED from the Reviewer, make no further edits and end your turn. Remain available: if the Orchestrator subsequently sends Executive Reviewer findings, resume work and address them."
}
```

---

### Step 3: Two-Tier Inter-Agent Communication Protocol

Inter-agent messages MUST be sent using `write_agent` and monitored using `read_agent`.

#### Tool Schema Specifications

1. **`write_agent` Schema**:
   - `agent_id` (string, required): The target background agent ID (e.g. `<REVIEWER_AGENT_ID>`, `<CODER_AGENT_ID>`, `<EXECUTIVE_REVIEWER_AGENT_ID>`).
   - `message` (string, required): Message text delivered as a new conversation turn to the recipient agent.

2. **`read_agent` Schema**:
   - `agent_id` (string, required): The target background agent ID to inspect.
   - `wait` (boolean, optional): Set to `true` to wait for agent completion or output.
   - `timeout` (number, optional): Wait timeout in seconds (default `30`, max `180`).
   - `since_turn` (integer, optional): Omit on first call; set 0-based index only to re-read earlier turns.

---

#### Tier A: Inner Iteration Protocol (Coder <-> Reviewer)

1. **Coder Submission**:
   - `coder-agent` completes code edits and submits to `reviewer-agent`:
     ```typescript
     write_agent({
       agent_id: "<REVIEWER_AGENT_ID>",
       message: "I have applied code changes for [Task Title]. Please review the complete git diff surface and run targeted tests."
     })
     ```

2. **Reviewer Audit & Response**:
   - `reviewer-agent` captures the complete diff surface:
     ```bash
     git add -N . && git --no-pager diff HEAD && git status --porcelain
     ```
   - **If defects are found**:
     ```typescript
     write_agent({
       agent_id: "<CODER_AGENT_ID>",
       message: "VERDICT: REJECTED\nDefects found:\n1. [src/services/user.ts:42] Missing null check on request payload.\n2. [src/controllers/auth.ts:15] Unhandled promise rejection.\nPlease resolve these issues and re-submit."
     })
     ```
   - **If code is clean**:
     ```typescript
     write_agent({
       agent_id: "<CODER_AGENT_ID>",
       message: "VERDICT: APPROVED. All checks and tests passed cleanly with zero defects."
     })
     ```

3. **Orchestrator Parsing & Verdict Recognition**:
   - The Orchestrator monitors using `read_agent({ agent_id: "<REVIEWER_AGENT_ID>", wait: true, timeout: 60 })`.
   - **Verdict Token Recognition**: The Orchestrator MUST parse reviewer responses for explicit verdict tokens (`VERDICT: APPROVED`, `VERDICT: REJECTED`) as well as native natural-language approval phrases (e.g., "no significant issues found", "looks good to merge", "all checks pass").

---

#### Tier B: Outer Executive Review Protocol

Once `reviewer-agent` outputs `VERDICT: APPROVED` (or a native approval phrase) in Tier A:

1. **Orchestrator Handoff to Executive Reviewer**:
   - Orchestrator captures the current complete `git diff` surface (`git add -N . && git --no-pager diff HEAD`).
   - Orchestrator invokes `write_agent` to request executive review:
     ```typescript
     write_agent({
       agent_id: "<EXECUTIVE_REVIEWER_AGENT_ID>",
       message: "The Inner Loop (Coder + Reviewer) has approved the changes. Please perform an Executive Code & Architecture Review on the current complete git diff:\n\n<INSERT_GIT_DIFF_SUMMARY>\n\nOutput 'VERDICT: APPROVED' if accepted, or list detailed executive defect findings."
     })
     ```
   - **Large diff handling**: if the diff exceeds a reasonable message size, send a per-file summary plus the most security- and architecture-relevant hunks rather than truncating mid-hunk.

2. **Orchestrator Evaluation of Executive Review**:
   - Orchestrator reads `executive-reviewer-agent` output via `read_agent`.
   - The Orchestrator parses responses for `VERDICT: APPROVED` / native approval phrases vs `VERDICT: REJECTED`.

3. **Outcome Processing**:
   - **Case B1: Executive Approval (`VERDICT: APPROVED` or native approval)**:
     - Outer loop converges. Proceed immediately to Step 6 (Final Summary Report).
   - **Case B2: Executive Rejection (`VERDICT: REJECTED`)**:
     - Orchestrator captures the executive feedback and routes it directly back to `coder-agent`:
       ```typescript
       write_agent({
         agent_id: "<CODER_AGENT_ID>",
         message: "The Executive Reviewer reviewed the code and requested architectural changes:\n\n<INSERT_EXECUTIVE_FEEDBACK>\n\nPlease address these findings, apply edits, and submit updated changes to reviewer-agent for Inner Loop re-review."
       })
       ```
     - Reset the inner loop iteration counter to `0` and restart Tier A.

---

### Step 4: Convergence Criteria, Iteration Caps & Timeout Handling

#### 1. Convergence Criteria
The multi-agent loop achieves **Full Convergence** ONLY when both criteria are met:
1. `reviewer-agent` issues `VERDICT: APPROVED` (or a native approval phrase) in Tier A.
2. `executive-reviewer-agent` issues `VERDICT: APPROVED` (or a native approval phrase) in Tier B.

#### 2. Max Iteration Caps
To prevent infinite communication loops and resource exhaustion:
- **Inner Loop Limit**: Maximum **10 iterations** per inner loop cycle between `coder-agent` and `reviewer-agent`.
- **Outer Loop Limit**: Maximum **10 outer review cycles** with `executive-reviewer-agent`.
- **Global Safety Cap**: Maximum **3 full outer resets**. If the same defect class is reported in three consecutive outer cycles, stop and escalate to the user rather than looping.

#### 3. Timeout & Polling Strategy
- Use `read_agent` with `wait: true` and `timeout: 30` or `timeout: 60` seconds to monitor sub-agent progress.
- If an agent is in `running` state for longer than **180 seconds** without producing output:
  1. Poll `read_agent` without `wait` to inspect turn status.
  2. Send a nudge prompt via `write_agent(agent_id: "<id>", message: "Status check: Please report progress or output verdict.")`.
  3. If still unresponsive or in `failed` status, log the error state and ask the user whether to retry or proceed manually.

---

### Step 5: Edge Case Resolution & Safety Controls

| Edge Case / Scenario | Action / Fallback Protocol |
| :--- | :--- |
| **Not a git repository** | Warn the user that diff-based review is unavailable. Offer to run `git init` or fall back to reviewing explicitly listed changed files. |
| **Unclean Working Directory** | Before starting the loop, verify `git status --porcelain`. If uncommitted manual changes exist, ask the user before stashing. If approved, run `git stash push -u -m "agentic-loop-<timestamp>"` to preserve untracked and modified files, and report the stash ref so it can be restored. |
| **No test command discovered** | Downgrade the testing strategy to static review only and state this explicitly in the final report. Never install a new test framework to satisfy the loop. |
| **Conflicting Feedback (Inner vs Outer)** | Executive Reviewer feedback takes precedence over Inner Reviewer preferences. |
| **Test Failures vs Static Review** | Test failures are treated as blocking defects (`VERDICT: REJECTED`). |
| **Non-Blocking Warnings / Nits** | Reviewer may issue `VERDICT: APPROVED with non-blocking suggestions`. The inner loop can proceed to Tier B. |
| **Sub-Agent Crash or Failure** | If `read_agent` returns `status: "failed"` or `cancelled`, the Orchestrator re-spawns the sub-agent using `task` (maximum 2 re-spawns per role, then escalate to the user). |
| **Cap Exceeded Without Convergence** | Pause the loop, present the current diff and unresolved feedback to the user, and ask for manual direction. |
| **Secrets in the diff** | Any reviewer that detects credentials, tokens, or keys in the diff MUST issue `VERDICT: REJECTED` immediately and the Orchestrator must surface this to the user. |

---

### Step 6: Final Report to User

When the loop terminates (via Full Convergence or Cap Exceeded), present a clean, concise summary to the user:

```markdown
### 🤖 Multi-Agent Loop Execution Summary

- **Overall Status**: ✅ Fully Approved (Inner Loop + Executive Review)
- **Inner Loop Iterations**: 2 cycles (Coder ↔ Reviewer)
- **Outer Executive Review**: 1 cycle
- **Testing Strategy**: Executed targeted unit tests - 100% passing

#### Key Changes Applied:
1. `src/services/user.service.ts`: Added payload validation & null safety checks.
2. `src/services/user.service.test.ts`: Added unit test coverage for invalid payloads.

#### Audit Trail:
- **Inner Reviewer**: Approved after iteration 2 fix.
- **Executive Reviewer**: Approved architectural design & security posture.
```
