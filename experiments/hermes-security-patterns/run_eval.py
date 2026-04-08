"""Evaluate security controls against fullsend-specific attack payloads.

Static scanning (unicode, context injection) is delegated to Tirith CLI.
Secret redaction is handled by the PostToolUse hook (hooks/secret_redact_posttool.py).
SSRF protection is handled by the PreToolUse hook (hooks/ssrf_pretool.py).

Usage:
    # Full evaluation (requires tirith in PATH)
    uv run python run_eval.py

    # Hook tests only (no tirith needed)
    uv run python run_eval.py --hooks-only

    # Tirith scan tests only
    uv run python run_eval.py --tirith-only
"""

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import yaml

PAYLOADS_DIR = Path(__file__).parent / "payloads"
SSRF_HOOK_PATH = Path(__file__).parent / "hooks" / "ssrf_pretool.py"
REDACT_HOOK_PATH = Path(__file__).parent / "hooks" / "secret_redact_posttool.py"


def load_payloads() -> list[dict]:
    payloads = []
    for path in sorted(PAYLOADS_DIR.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        data["_file"] = path.name
        payloads.append(data)
    return payloads


# ---------------------------------------------------------------------------
# Tirith scan evaluation (unicode, context injection, secrets)
# ---------------------------------------------------------------------------


def tirith_available() -> bool:
    try:
        subprocess.run(
            ["tirith", "--version"],
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def eval_tirith_file_scan(payload: dict) -> dict:
    """Write payload content to a temp file and run tirith scan on it."""
    # Determine the text content and temp filename
    if payload.get("scanner") == "context_injection":
        content = payload["content"]
        suffix = payload.get("filename", "AGENTS.md")
    elif payload.get("scanner") == "unicode_normalizer":
        content = payload["text"]
        suffix = "input.txt"
    elif payload.get("scanner") == "secret_redactor":
        content = payload["text"]
        suffix = "output.txt"
    else:
        return {}

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=f"_{suffix}", delete=False
    ) as f:
        f.write(content)
        tmp_path = f.name

    start = time.perf_counter()
    try:
        result = subprocess.run(
            ["tirith", "scan", "--json", "--", tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        # tirith exit codes: 0=clean, 1=findings, 2=warn
        detected = result.returncode != 0

        findings = []
        if result.stdout.strip():
            try:
                scan_output = json.loads(result.stdout)
                if isinstance(scan_output, list):
                    findings = scan_output
                elif isinstance(scan_output, dict):
                    findings = scan_output.get("findings", [])
            except json.JSONDecodeError:
                findings = [{"raw": result.stdout.strip()}]

    except subprocess.TimeoutExpired:
        elapsed_ms = (time.perf_counter() - start) * 1000
        detected = False
        findings = [{"error": "tirith scan timed out"}]
    except FileNotFoundError:
        return {
            "name": payload["name"],
            "scanner": f"tirith:{payload['scanner']}",
            "detected": False,
            "expected": True,
            "correct": False,
            "error": "tirith not found in PATH",
            "latency_ms": 0,
        }
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    scanner_name = payload.get("scanner", "unknown")
    expected_map = {
        "context_injection": "blocked",
        "unicode_normalizer": "normalized",
    }
    expected = payload.get("expected") == expected_map.get(scanner_name, "detected")

    return {
        "name": payload["name"],
        "scanner": f"tirith:{scanner_name}",
        "detected": detected,
        "expected": expected,
        "correct": detected == expected,
        "finding_count": len(findings),
        "findings": findings[:5],
        "latency_ms": elapsed_ms,
    }


def eval_tirith(payloads: list[dict]) -> list[dict]:
    """Run tirith scan against all static-scanning payloads."""
    results = []
    tirith_scanners = {"context_injection", "unicode_normalizer"}

    for p in payloads:
        if p.get("scanner") not in tirith_scanners:
            continue
        result = eval_tirith_file_scan(p)
        if result:
            results.append(result)

    return results


# ---------------------------------------------------------------------------
# SSRF hook evaluation
# ---------------------------------------------------------------------------


def eval_ssrf_hook(payloads: list[dict]) -> list[dict]:
    """Test the PreToolUse SSRF hook against SSRF payloads."""
    results = []

    for p in payloads:
        if p.get("scanner") != "ssrf_validator":
            continue

        urls = p.get("urls", [])
        any_blocked = False
        url_results = []

        start = time.perf_counter()

        # Test each URL as a WebFetch tool call
        for url in urls:
            hook_input = json.dumps({
                "tool_name": "WebFetch",
                "tool_input": {"url": url},
            })

            try:
                proc = subprocess.run(
                    [sys.executable, str(SSRF_HOOK_PATH)],
                    input=hook_input,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                blocked = proc.returncode != 0
                reason = ""
                if proc.stdout.strip():
                    try:
                        out = json.loads(proc.stdout)
                        reason = out.get("reason", "")
                    except json.JSONDecodeError:
                        reason = proc.stdout.strip()
            except subprocess.TimeoutExpired:
                blocked = False
                reason = "hook timed out"

            url_results.append({"url": url, "blocked": blocked, "reason": reason})
            if blocked:
                any_blocked = True

        # Test redirect chain as a Bash curl command
        chain = p.get("redirect_chain", [])
        chain_results = []
        if chain:
            for chain_url in chain:
                hook_input = json.dumps({
                    "tool_name": "Bash",
                    "tool_input": {"command": f"curl -sL {chain_url}"},
                })
                proc = subprocess.run(
                    [sys.executable, str(SSRF_HOOK_PATH)],
                    input=hook_input,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                blocked = proc.returncode != 0
                reason = ""
                if proc.stdout.strip():
                    try:
                        out = json.loads(proc.stdout)
                        reason = out.get("reason", "")
                    except json.JSONDecodeError:
                        reason = proc.stdout.strip()
                chain_results.append(
                    {"url": chain_url, "blocked": blocked, "reason": reason}
                )
                if blocked:
                    any_blocked = True

        elapsed_ms = (time.perf_counter() - start) * 1000
        expected = p.get("expected") == "blocked"

        results.append({
            "name": p["name"],
            "scanner": "ssrf_hook",
            "detected": any_blocked,
            "expected": expected,
            "correct": any_blocked == expected,
            "url_results": url_results,
            "chain_results": chain_results,
            "latency_ms": elapsed_ms,
        })

    return results


# ---------------------------------------------------------------------------
# Secret redaction hook evaluation
# ---------------------------------------------------------------------------


def eval_redact_hook(payloads: list[dict]) -> list[dict]:
    """Test the PostToolUse secret redaction hook against secret payloads."""
    results = []

    for p in payloads:
        if p.get("scanner") != "secret_redactor":
            continue

        text = p["text"]

        start = time.perf_counter()

        hook_input = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "echo output"},
            "tool_result": text,
        })

        try:
            proc = subprocess.run(
                [sys.executable, str(REDACT_HOOK_PATH)],
                input=hook_input,
                capture_output=True,
                text=True,
                timeout=5,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000

            detected = False
            redacted_text = ""
            findings = []

            if proc.stdout.strip():
                try:
                    out = json.loads(proc.stdout)
                    redacted_text = out.get("tool_result", "")
                    meta = out.get("metadata", {})
                    count = meta.get("secrets_redacted", 0)
                    patterns = meta.get("patterns", [])
                    detected = count > 0
                    findings = patterns
                except json.JSONDecodeError:
                    pass

        except subprocess.TimeoutExpired:
            elapsed_ms = (time.perf_counter() - start) * 1000
            detected = False
            findings = []
            redacted_text = ""

        expected = p.get("expected") == "detected"

        results.append({
            "name": p["name"],
            "scanner": "redact_hook",
            "detected": detected,
            "expected": expected,
            "correct": detected == expected,
            "finding_count": len(findings),
            "findings": findings[:5],
            "redacted_preview": redacted_text[:200] if redacted_text else "",
            "latency_ms": elapsed_ms,
        })

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_results(all_results: list[dict]):
    print(f"\n{'=' * 100}")
    print("  HERMES SECURITY PATTERNS EVALUATION")
    print(f"{'=' * 100}")

    by_scanner: dict[str, list[dict]] = {}
    for r in all_results:
        by_scanner.setdefault(r["scanner"], []).append(r)

    for scanner, results in sorted(by_scanner.items()):
        print(f"\n--- {scanner} ---")
        for r in results:
            if r.get("error"):
                print(f"  [ERROR] {r['name']:<40} {r['error']}")
                continue

            status = "PASS" if r["correct"] else "FAIL"
            det = "DETECTED" if r["detected"] else "CLEAN"
            exp = "expected" if r["correct"] else "UNEXPECTED"
            print(
                f"  [{status}] {r['name']:<40} {det:<10} "
                f"({exp}, {r['latency_ms']:.1f}ms)"
            )

            # Show URL-level details for SSRF
            if r.get("url_results"):
                for ur in r["url_results"]:
                    bl = "BLOCKED" if ur["blocked"] else "ALLOWED"
                    print(f"         {bl:<8} {ur['url']}")
                    if ur.get("reason"):
                        print(f"                  -> {ur['reason']}")

            # Show redacted preview
            if r.get("redacted_preview"):
                print(f"         redacted: {r['redacted_preview'][:80]}...")

            # Show tirith findings
            if r.get("findings") and r.get("finding_count", 0) > 0:
                for f in r["findings"][:3]:
                    if isinstance(f, dict):
                        rule = f.get("rule_id", f.get("raw", ""))
                        sev = f.get("severity", "")
                        msg = f.get("message", f.get("detail", ""))
                        print(f"         [{sev}] {rule}: {msg}")
                    else:
                        print(f"         {f}")

    # Summary
    print(f"\n{'=' * 100}")
    print("  SUMMARY")
    print(f"{'=' * 100}")

    total = len(all_results)
    errors = sum(1 for r in all_results if r.get("error"))
    correct = sum(1 for r in all_results if r["correct"])
    testable = total - errors
    avg_latency = (
        sum(r["latency_ms"] for r in all_results if not r.get("error")) / testable
        if testable
        else 0
    )

    print(f"\n  Total payloads:  {total}")
    if errors:
        print(f"  Errors:          {errors}")
    print(f"  Correct:         {correct}/{testable} ({100 * correct / testable:.0f}%)")
    print(f"  Avg latency:     {avg_latency:.1f}ms")

    for scanner, results in sorted(by_scanner.items()):
        errs = sum(1 for r in results if r.get("error"))
        n = len(results) - errs
        c = sum(1 for r in results if r["correct"])
        avg = sum(r["latency_ms"] for r in results if not r.get("error")) / n if n else 0
        print(f"\n  {scanner}:")
        print(f"    Correct: {c}/{n} ({100 * c / n:.0f}%)" if n else f"    Skipped (errors)")
        print(f"    Avg latency: {avg:.1f}ms")

    if correct < testable:
        print("\n  FAILURES:")
        for r in all_results:
            if not r.get("error") and not r["correct"]:
                print(f"    - {r['name']} ({r['scanner']})")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate Hermes security patterns")
    parser.add_argument(
        "--hooks-only", action="store_true", help="Only test hooks (no tirith)"
    )
    parser.add_argument(
        "--tirith-only", action="store_true", help="Only test tirith scan"
    )
    args = parser.parse_args()

    payloads = load_payloads()
    print(f"Loaded {len(payloads)} payloads from {PAYLOADS_DIR}")

    all_results = []

    if not args.hooks_only:
        if tirith_available():
            print("Using tirith CLI for static scanning")
            all_results.extend(eval_tirith(payloads))
        else:
            print("WARNING: tirith not found in PATH, skipping static scan tests")
            print("  Install: brew install sheeki03/tap/tirith")

    if not args.tirith_only:
        if SSRF_HOOK_PATH.exists():
            print(f"Using SSRF hook: {SSRF_HOOK_PATH}")
            all_results.extend(eval_ssrf_hook(payloads))
        else:
            print(f"WARNING: SSRF hook not found at {SSRF_HOOK_PATH}")

        if REDACT_HOOK_PATH.exists():
            print(f"Using redact hook: {REDACT_HOOK_PATH}")
            all_results.extend(eval_redact_hook(payloads))
        else:
            print(f"WARNING: Redact hook not found at {REDACT_HOOK_PATH}")

    if not all_results:
        print("\nNo tests ran. Install tirith or check hook path.")
        sys.exit(1)

    print_results(all_results)

    if not all(r.get("error") or r["correct"] for r in all_results):
        sys.exit(1)


if __name__ == "__main__":
    main()
