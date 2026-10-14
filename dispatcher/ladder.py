"""The tier ladder: plan once, execute with attempts, escalate on failure, review only when the
gate asks. Tiers are shell commands resolved from `.ds/agent.toml`; `dry` runs nothing, so the
acceptance command alone decides, which is what proves the plumbing.

An escalation never sends the repository: only the spec, the diff, and the test output.
"""
from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .queue import Task

DEFAULT_TIERS = {"execute": "cortex:sonnet", "plan": "cortex:opus", "review": "cortex:opus"}


@dataclass
class TierResult:
    tier: str
    ok: bool
    output: str
    tokens: int | None = None


@dataclass
class Outcome:
    task: Task
    closed_tier: str | None
    attempts: int
    escalations: int
    tests_passed: bool
    tokens: dict[str, int] = field(default_factory=dict)
    gate_confidence: float = 0.0
    review_verdict: str = ""
    needs_human: str = ""
    test_output: str = ""


def load_agent_config(repo: Path) -> dict:
    p = repo / ".ds" / "agent.toml"
    cfg = tomllib.loads(p.read_text()) if p.exists() else {}
    tiers = {**DEFAULT_TIERS, **cfg.get("tiers", {})}
    limits = {"max_attempts": 3, **cfg.get("limits", {})}
    return {"tiers": tiers, "limits": limits}


def _tokens_from(text: str) -> int | None:
    m = re.search(r"(?:total|tokens?)[^\d]{0,20}(\d{2,8})", text, re.I)
    return int(m.group(1)) if m else None


def run_tier(spec: str, worktree: Path, prompt: str, timeout: int = 900) -> TierResult:
    """`dry` does nothing. `cortex:<model>` shells out to Cortex Code headless; `opencode:<model>`
    to OpenCode. Both shapes are from docs/agent-system.md and unverified on this machine."""
    provider, _, model = spec.partition(":")
    if provider == "dry":
        return TierResult("dry", True, "dry tier: no model, no edits", 0)
    if provider == "cortex":
        cmd = ["cortex", "--print", "--mode", "code"] + (["--model", model] if model else []) + [prompt]
    elif provider == "opencode":
        cmd = ["opencode", "run", "--model", model, prompt]
    else:
        return TierResult(spec, False, f"unknown tier provider {provider!r}")
    try:
        r = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return TierResult(spec, False, f"{cmd[0]}: {e}")
    out = r.stdout + r.stderr
    return TierResult(spec, r.returncode == 0, out[-4000:], _tokens_from(out))


def accept(worktree: Path, cmd: str) -> tuple[bool, str]:
    r = subprocess.run(cmd, shell=True, cwd=worktree, capture_output=True, text=True, timeout=600)
    return r.returncode == 0, (r.stdout + r.stderr)[-2000:]


def escalation_payload(task: Task, diff_text: str, test_output: str) -> str:
    return (f"Task: {task.text}\nDefinition of done: `{task.accept}` exits 0.\n\n"
            f"Diff so far:\n{diff_text[-6000:]}\n\nTest output:\n{test_output[-2000:]}\n")


def run_ladder(task: Task, worktree: Path, cfg: dict, tier_override: str | None = None, diff_fn=None) -> Outcome:
    tiers = cfg["tiers"]
    if tier_override:
        tiers = {k: tier_override for k in tiers}
    max_attempts = int(cfg["limits"]["max_attempts"])
    tokens: dict[str, int] = {}
    prompt = f"{task.text} Definition of done: `{task.accept}` exits 0."
    attempts = escalations = 0
    last_out = ""

    # plan: one call at the plan tier, only when it is a model
    if not tiers["plan"].startswith("dry"):
        p = run_tier(tiers["plan"], worktree, "Plan only, no edits: " + prompt)
        tokens["plan"] = (tokens.get("plan", 0) + (p.tokens or 0))
        if p.ok and p.output.strip():
            prompt = p.output.strip()[:4000] + "\n\n" + prompt

    # execute with attempts
    for attempts in range(1, max_attempts + 1):
        r = run_tier(tiers["execute"], worktree, prompt)
        tokens["execute"] = tokens.get("execute", 0) + (r.tokens or 0)
        ok, last_out = accept(worktree, task.accept)
        if ok:
            confidence = 1.0 if attempts == 1 else 0.6
            verdict = ""
            if confidence < 0.8 and not tiers["review"].startswith("dry"):
                rv = run_tier(tiers["review"], worktree, "Review this diff for correctness; answer APPROVE or REJECT with one reason:\n" + (diff_fn(worktree) if diff_fn else ""))
                tokens["review"] = tokens.get("review", 0) + (rv.tokens or 0)
                verdict = rv.output.strip()[:200]
            return Outcome(task, tiers["execute"], attempts, 0, True, tokens, confidence, verdict, test_output=last_out)

    # escalate once: payload only
    escalations = 1
    e = run_tier(tiers["review"], worktree, escalation_payload(task, diff_fn(worktree) if diff_fn else "", last_out))
    tokens["escalate"] = tokens.get("escalate", 0) + (e.tokens or 0)
    ok, last_out = accept(worktree, task.accept)
    if ok:
        return Outcome(task, tiers["review"], attempts, escalations, True, tokens, 0.5, test_output=last_out)
    needs = f"`{task.accept}` still fails after {attempts} attempt(s) and 1 escalation. Last output: {last_out.strip()[-300:]}"
    return Outcome(task, None, attempts, escalations, False, tokens, 0.0, needs_human=needs, test_output=last_out)
