#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6.0"]
# ///
"""Skill eval framework — run evals against AI agent CLIs.

Usage:
    uv run --script hack/evals/run.py                        # all skills
    uv run --script hack/evals/run.py --skill filing-issues  # one skill
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
WORKSPACE_DIR = REPO_ROOT / ".eval-workspace"

# {eval_id: {agent: {config: summary_dict}}}
EvalResults = dict[str, dict[str, dict[str, Any]]]

MUTATION_PROMPT = """You are generating a variant of a test case for an AI skill evaluation.

Rephrase both the user prompt and the expected behavior description below.
Change the wording, phrasing, and specific details (names, scenarios,
error descriptions) while preserving the core intent and the behaviors
being tested. The variant should test the same capability but with
different surface-level details.

## Original prompt
{prompt}

## Original expected behavior
{expected}

Respond with ONLY a YAML object (no markdown fences, no extra text):
prompt: "the rephrased user prompt"
expected: "the rephrased expected behavior"
"""

GRADING_PROMPT = """You are a strict evaluator for an AI coding agent. You are judging
whether the agent's actual output demonstrates the expected behaviors.

## Expected behavior
{expected}

## Actual agent output
{output}

Does the actual output satisfy the expected behavior? Be strict but fair.
The output does not need to match word-for-word — it needs to demonstrate
the described behaviors and meet the described criteria.

Respond with ONLY a YAML object (no markdown fences, no extra text):
pass: true or false
evidence: "quotes from the output that support your judgment, or what is missing"
"""


# ---------------------------------------------------------------------------
# Runner: invoke AI CLIs non-interactively
# ---------------------------------------------------------------------------


def available_agents() -> list[str]:
    """Return list of installed agent CLIs."""
    agents: list[str] = []
    if shutil.which("claude"):
        agents.append("claude")
    if shutil.which("opencode"):
        agents.append("opencode")
    return agents


def run_agent(agent: str, prompt: str, skill_content: str | None = None) -> str | None:
    """Run an agent CLI with the given prompt. Returns output or None on failure."""
    full_prompt = f"{skill_content}\n\n---\n\n{prompt}" if skill_content else prompt
    if agent == "claude":
        return _run_claude(full_prompt)
    if agent == "opencode":
        return _run_opencode(full_prompt)
    print(f"  WARNING: Unknown agent '{agent}', skipping")
    return None


def _run_claude(prompt: str) -> str | None:
    """Run Claude Code non-interactively with Read-only sandbox."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--allowedTools", "Read"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        return result.stdout.strip() if result.stdout else result.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        print(f"  WARNING: claude runner failed: {e}")
        return None


def _run_opencode(prompt: str) -> str | None:
    """Run OpenCode non-interactively.

    TODO: OpenCode does not have an --allowedTools equivalent. Add sandboxing
    (e.g., a custom agent config that restricts tool access) when available.
    The runner interface is structured so adding sandboxing later requires no
    architectural changes — just modify this function.
    """
    try:
        result = subprocess.run(
            ["opencode", "run", "-q", prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.stdout.strip() if result.stdout else result.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        print(f"  WARNING: opencode runner failed: {e}")
        return None


# ---------------------------------------------------------------------------
# YAML response parsing (shared by mutator and grader)
# ---------------------------------------------------------------------------


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from text."""
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        return "\n".join(lines)
    return text


# ---------------------------------------------------------------------------
# Mutator: generate rephrased variants of eval cases
# ---------------------------------------------------------------------------


def generate_mutations(
    prompt: str,
    expected: str,
    count: int,
    agent: str,
) -> list[dict[str, str]]:
    """Generate mutated variants of a prompt/expected pair."""
    mutations: list[dict[str, str]] = []
    for i in range(count):
        output = run_agent(agent, MUTATION_PROMPT.format(prompt=prompt, expected=expected))
        if output:
            parsed = _parse_yaml_pair(output, "prompt", "expected")
            if parsed:
                mutations.append(parsed)
                continue
            print(f"  WARNING: Failed to parse mutation {i + 1}, using original")
        else:
            print(f"  WARNING: Mutation {i + 1} generation failed, using original")
        mutations.append({"prompt": prompt, "expected": expected})
    return mutations


def _parse_yaml_pair(output: str, key_a: str, key_b: str) -> dict[str, str] | None:
    """Parse a YAML response expecting two string keys."""
    try:
        data = yaml.safe_load(_strip_fences(output.strip()))
        if isinstance(data, dict) and key_a in data and key_b in data:
            return {key_a: str(data[key_a]), key_b: str(data[key_b])}
    except yaml.YAMLError:
        pass
    return None


# ---------------------------------------------------------------------------
# Grader: LLM-as-judge
# ---------------------------------------------------------------------------


def grade(agent: str, output: str, expected: str) -> dict[str, Any] | None:
    """Grade agent output against expected behavior. Returns {passed, evidence} or None."""
    response = run_agent(agent, GRADING_PROMPT.format(expected=expected, output=output))
    if not response:
        return None
    text = _strip_fences(response.strip())
    try:
        data = yaml.safe_load(text)
        if isinstance(data, dict) and "pass" in data:
            return {"passed": bool(data["pass"]), "evidence": str(data.get("evidence", ""))}
    except yaml.YAMLError:
        pass
    return None


# ---------------------------------------------------------------------------
# Report: aggregation + stdout summary
# ---------------------------------------------------------------------------


def print_summary(skill_name: str, results: EvalResults) -> bool:
    """Print human-readable summary and return True if all cases pass."""
    print(f"\n=== Skill Eval Results: {skill_name} ===\n")

    all_passing = True
    failures: list[str] = []
    case_ids = list(results.keys())

    for eval_id in case_ids:
        agents = results[eval_id]
        threshold: float = 0.9
        for agent_data in agents.values():
            if "with_skill" in agent_data:
                threshold = agent_data["with_skill"]["threshold"]
                break

        case_pass = True
        print(f"  {eval_id} (threshold: {threshold:.2f})")
        for agent in sorted(agents.keys()):
            configs = agents[agent]
            ws: dict[str, Any] = configs.get("with_skill", {})
            wo: dict[str, Any] = configs.get("without_skill", {})
            ws_rate: float = ws.get("pass_rate", 0.0)
            ws_met: bool = ws.get("met_threshold", False)
            wo_rate: float = wo.get("pass_rate", 0.0)
            pct = f"{ws_rate * 100:.0f}%"
            status = "PASS" if ws_met else "FAIL (below threshold)"
            delta = ws_rate - wo_rate
            delta_str = f"+{delta * 100:.0f}%" if delta >= 0 else f"{delta * 100:.0f}%"
            print(f"    {agent}:")
            print(
                f"      with_skill:    {ws.get('passed', 0)}/{ws.get('total', 0)}"
                f" passed ({pct}) -- {status}"
            )
            print(
                f"      without_skill: {wo.get('passed', 0)}/{wo.get('total', 0)}"
                f" passed ({wo_rate * 100:.0f}%)"
            )
            print(f"      delta: {delta_str}")
            if not ws_met:
                case_pass = False
                failures.append(
                    f"{eval_id}: {agent} with_skill below threshold ({pct} < {threshold:.0%})"
                )
        if not case_pass:
            all_passing = False
        print()

    passing = [eid for eid in case_ids if _case_passes(results[eid])]
    print("  Summary:")
    print(f"    Total cases:    {len(case_ids)}")
    print(f"    Cases passing:  {len(passing)}" + (f" ({', '.join(passing)})" if passing else ""))
    print(f"    Cases failing:  {len(case_ids) - len(passing)}")
    for f in failures:
        print(f"      {f}")
    print()
    print("=== PASSED ===" if all_passing else "=== FAILED ===")
    return all_passing


def _case_passes(agents: dict[str, dict[str, Any]]) -> bool:
    """Check if a case passes across all agents."""
    return all(
        agent_data.get("with_skill", {}).get("met_threshold", False)
        for agent_data in agents.values()
    )


# ---------------------------------------------------------------------------
# Main: discover skills, run evals, report results
# ---------------------------------------------------------------------------


def discover_skills(skill_filter: str | None = None) -> list[Path]:
    """Find all skills with evals/evals.yaml."""
    if not SKILLS_DIR.is_dir():
        return []
    return [
        d
        for d in sorted(SKILLS_DIR.iterdir())
        if d.is_dir()
        and (d / "evals" / "evals.yaml").exists()
        and (skill_filter is None or d.name == skill_filter)
    ]


def run_eval_case(
    eval_case: dict[str, Any],
    skill_content: str,
    agents: list[str],
    default_threshold: float,
    workspace: Path,
) -> dict[str, dict[str, Any]]:
    """Run a single eval case against all agents and configurations."""
    eval_id: str = eval_case["id"]
    prompt: str = eval_case["prompt"]
    expected: str = eval_case["expected"]
    num_mutations: int = eval_case.get("mutations", 5)
    threshold: float = float(eval_case.get("threshold", default_threshold))

    print(f"\n--- Eval: {eval_id} ---")
    mutation_agent = agents[0]
    print(f"  Generating {num_mutations} mutations using {mutation_agent}...")
    mutations = generate_mutations(prompt, expected, num_mutations, mutation_agent)

    test_cases: list[dict[str, str]] = [{"prompt": prompt, "expected": expected}]
    test_cases.extend(mutations)

    agent_results: dict[str, dict[str, Any]] = {}
    for agent in agents:
        agent_results[agent] = {}
        for config in ("with_skill", "without_skill"):
            skill_ctx = skill_content if config == "with_skill" else None
            mutation_results: list[dict[str, Any]] = []
            passed_count = 0
            failed_count = 0
            skipped_count = 0

            print(f"  {agent} / {config}: running {len(test_cases)} variants...")
            for i, tc in enumerate(test_cases):
                entry: dict[str, Any] = {
                    "mutation": i,
                    "prompt": tc["prompt"],
                    "expected": tc["expected"],
                }
                output = run_agent(agent, tc["prompt"], skill_ctx)
                if output is None:
                    entry.update(passed=False, evidence="Agent produced no output")
                    skipped_count += 1
                else:
                    result = grade(agent, output, tc["expected"])
                    if result is None:
                        entry.update(passed=False, evidence="Grading failed")
                        skipped_count += 1
                    else:
                        entry.update(passed=result["passed"], evidence=result["evidence"])
                        if result["passed"]:
                            passed_count += 1
                        else:
                            failed_count += 1
                mutation_results.append(entry)

            denominator = passed_count + failed_count
            pass_rate = passed_count / denominator if denominator > 0 else 0.0
            summary: dict[str, Any] = {
                "total": len(test_cases),
                "passed": passed_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "pass_rate": pass_rate,
                "threshold": threshold,
                "met_threshold": pass_rate >= threshold,
            }

            case_dir = workspace / eval_id / agent / config
            case_dir.mkdir(parents=True, exist_ok=True)
            with open(case_dir / "grading.yaml", "w") as f:
                yaml.dump(
                    {
                        "eval_id": eval_id,
                        "agent": agent,
                        "configuration": config,
                        "mutations": mutation_results,
                        "summary": summary,
                    },
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                )
            agent_results[agent][config] = summary
            status = "PASS" if summary["met_threshold"] else "FAIL"
            if config == "with_skill":
                print(
                    f"    {config}: {passed_count}/{len(test_cases)} ({pass_rate:.0%}) [{status}]"
                )
            else:
                print(f"    {config}: {passed_count}/{len(test_cases)} ({pass_rate:.0%})")
    return agent_results


def main() -> int:
    parser = argparse.ArgumentParser(description="Run skill evals")
    parser.add_argument("--skill", help="Run evals for a specific skill only")
    args = parser.parse_args()

    agents = available_agents()
    if not agents:
        print("ERROR: No agent CLIs found (need 'claude' or 'opencode' on PATH)")
        return 1
    print(f"Available agents: {', '.join(agents)}")

    skills = discover_skills(args.skill)
    if not skills:
        msg = f"No evals found for skill '{args.skill}'" if args.skill else "No skills with evals"
        print(f"ERROR: {msg}")
        return 1

    all_passing = True
    for skill_dir in skills:
        evals_data: dict[str, Any] = yaml.safe_load(
            (skill_dir / "evals" / "evals.yaml").read_text()
        )
        skill_name: str = evals_data.get("skill_name", skill_dir.name)
        default_threshold = float(evals_data.get("threshold", 0.9))
        eval_cases: list[dict[str, Any]] = evals_data.get("evals", [])
        skill_content = (skill_dir / "SKILL.md").read_text()

        print(f"\n{'=' * 60}")
        print(f"Skill: {skill_name} ({len(eval_cases)} cases)")
        print(f"{'=' * 60}")

        workspace = WORKSPACE_DIR / skill_name
        workspace.mkdir(parents=True, exist_ok=True)
        all_results: EvalResults = {}

        for case in eval_cases:
            all_results[case["id"]] = run_eval_case(
                case,
                skill_content,
                agents,
                default_threshold,
                workspace,
            )

        if not print_summary(skill_name, all_results):
            all_passing = False

    return 0 if all_passing else 1


if __name__ == "__main__":
    sys.exit(main())
