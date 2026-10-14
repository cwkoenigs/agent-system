# agent-system

Hand work to an agent and get back a merge request, not a chat transcript.

You describe a small, test-gated change. Overnight, the dispatcher has Cortex do it in an isolated
copy of the repository, keeps only what makes the repository's own tests pass, and opens a merge
request with a one-paragraph summary. When it cannot finish, it tells you exactly what it needs.
Every task is measured, so you can see what this costs and whether it is worth it.

**Status: skeleton.** The loop runs end to end with a `dry` tier that makes no edits. The four
connections that make it useful are not wired yet: calling Cortex, reading GitLab issues, opening the
merge request, and posting the digest. See [What is left to wire](#what-is-left-to-wire).

## What a data scientist sees

Nothing new to learn. Two ways to hand work off:

```bash
ds task "add tests for load_claims and make coverage > 80%"
```

or label a GitLab issue `agent`. The next morning one of two things is waiting:

- **A merge request** with a summary you can read in ten seconds: what changed, which tier closed it,
  that the tests pass.
- **A comment on the issue** with a specific question: not "task failed" but "the 2024 cohort fixture
  is missing; what should the expected output be?"

Plus one short message per team per morning: what shipped overnight, what needs a human. Nobody
picks a model, sees a token count, or watches an agent work.

## Where it fits

This is the second half of the knowledge system. The first half (the canon, `.ds/manifest.toml`,
`ds reconcile`, `ds docs`) makes every repository say clearly which standards apply and how to test
it. The dispatcher relies on exactly that:

- The **test command** in a repository's `AGENTS.md` is the definition of done. A task without a
  mechanical pass or fail is not attempted; it goes to a person.
- The agent reads the **manifest and the standards in force** (through `ds serve-mcp`) before it reads
  any code, so its changes follow the team's rules without being told.
- **`.ds/agent.toml`**, written by `ds new`, sets which model tier does what and the budget per task.

## How a task flows

```
queue ──▶ worktree ──▶ plan (Opus, one call) ──▶ execute (Sonnet-class, up to N attempts)
                                                        │
                                       tests pass? ─────┼── yes ──▶ review only if unsure ──▶ MR + summary
                                                        │
                                                        no ──▶ escalate once (Opus) ──▶ pass: MR
                                                                                     └▶ fail: "needs you" comment
                                                     every task ──▶ metrics row ──▶ morning digest
```

1. **Queue.** Tasks come from GitLab issues labeled `agent`, or from a local `TASKS.yaml` for testing.
   Each task has a repository, a description, and an acceptance command that must exit 0.
2. **Worktree.** Each task gets its own git worktree on a branch `agent/<task-id>`, so tasks never
   collide and the main checkout is never touched. The worktree is removed afterwards.
3. **Plan.** One call to the strongest tier turns the task into a short spec. This is the only place a
   large model sees the task in full, and the input is small.
4. **Execute.** The cheaper tier makes the change, then the acceptance command runs. Up to
   `max_attempts` tries.
5. **Gate.** First-try passes are trusted. A pass that took several attempts gets one review call
   before it ships.
6. **Escalate.** If every attempt fails, the strongest tier gets one try. It receives the spec, the
   diff so far, and the test output, never the whole repository.
7. **Deliver.** A patch and a summary are written; the merge request carries them. A task that still
   fails produces a specific question instead.
8. **Measure.** One row per task: which tier closed it, attempts, escalations, tokens per tier, wall
   time, pass or fail. The digest is built from these rows.

## Tiers

Set per repository in `.ds/agent.toml`:

```toml
[tiers]
execute = "cortex:sonnet"   # does the work; retried
plan    = "cortex:opus"     # one call per task
review  = "cortex:opus"     # only when the gate asks, and for the single escalation

[limits]
max_attempts = 3
```

A tier is `provider:model`. Providers: `cortex` (Cortex Code headless), `opencode`, and `dry`, which
runs nothing so only the acceptance command decides. There is no local-model tier; Cortex is the floor.

## Try it now (no model, no credentials)

```bash
uv sync
uv run pytest                                   # the loop, end to end, with the dry tier

# against any directory of git repos and a TASKS.yaml:
uv run python -m dispatcher.run --once --tasks TASKS.yaml --repos ~/code --tier dry --out results/
uv run python -m dispatcher.digest --db results/metrics.db --results results/
```

`TASKS.yaml`:

```yaml
tasks:
  - id: cf-02
    repo: claims-features          # directory name under --repos
    type: tests
    text: Add tests for high_cost_cohort covering empty and mixed input.
    accept: test -f tests/test_cohorts.py && python -m pytest -q tests/test_cohorts.py
```

With the dry tier, a task passes only if its acceptance command already passes. That is the point: it
proves the queue, worktrees, gate, metrics, and digest work before any model is involved. Run over the
standards bench's 20 tasks, it records 20 rows and a digest of "20 need a human", each with the reason.

## What you get per task

`results/<task-id>/diff.patch` and `results/<task-id>/summary.md`, plus a row in `results/metrics.db`:

| Column | Meaning |
|---|---|
| `closed_tier` | which tier's work passed the tests, or empty if none did |
| `local_attempts`, `escalations` | how hard it had to try |
| `tokens_t1`, `tokens_t2` | tokens at the execute tier, and at the plan, review, and escalation tier |
| `tests_passed`, `gate_confidence`, `review_verdict` | the outcome and how sure the gate was |
| `wall_seconds` | time per task |

`results/to_snowflake.sql` is the DDL for mirroring the table to `DS_OPS.AGENT.TASKS`, so cost by
tier, repository, and person is one query.

## Code

| File | Does |
|---|---|
| `dispatcher/queue.py` | `Task`; `LocalQueue` (YAML); `GitLabQueue` (interface only) |
| `dispatcher/worktree.py` | create, diff, and clean a per-task worktree |
| `dispatcher/ladder.py` | tier config, `run_tier` (shells out per provider), acceptance, the plan/execute/gate/escalate loop |
| `dispatcher/metrics.py` | the SQLite table and the Snowflake DDL |
| `dispatcher/run.py` | `--once`: drain the queue, write patch and summary, record metrics |
| `dispatcher/digest.py` | the morning digest; Slack posting is a stub |

## What is left to wire

All four need the work machine, which has GitLab, Cortex, and Slack access. About a day.

| Piece | Where | What it needs |
|---|---|---|
| Call Cortex for real | `ladder.run_tier` | Confirm the headless invocation (`cortex --print --mode code` is the design's guess) and how it reports token usage |
| Read tasks from GitLab | `queue.GitLabQueue.pop_all` | `GITLAB_TOKEN`; list open issues labeled `agent`; take the acceptance command from the issue or the repo's `AGENTS.md` |
| Open the merge request | `run.process` | Push `agent/<task-id>`, open an MR with `summary.md` as the description, comment the link on the issue |
| Post the digest | `digest.post_slack` | A Slack webhook in `SLACK_WEBHOOK` |

Then schedule `python -m dispatcher.run --once` nightly on an always-on machine, or as an SPCS job.
`ds task` itself is not built yet; until it is, create the GitLab issue by hand.

## Design

The full design is `docs/design/agent-system.md` in the canon repository. This repository implements it
without the local-model tier, which was dropped.
