"""Evaluate all Hermes-inspired security scanners against fullsend-specific payloads.

Runs each scanner against its targeted payloads and reports detection rates,
false positives, and latency.
"""

import sys
import time
from pathlib import Path

import yaml
from scanners import ContextInjectionScanner, SecretRedactor, SSRFValidator, UnicodeNormalizer

PAYLOADS_DIR = Path(__file__).parent / "payloads"


def load_payloads() -> list[dict]:
    payloads = []
    for path in sorted(PAYLOADS_DIR.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        data["_file"] = path.name
        payloads.append(data)
    return payloads


def eval_secret_redactor(payloads: list[dict]) -> list[dict]:
    redactor = SecretRedactor()
    results = []

    for p in payloads:
        if p.get("scanner") != "secret_redactor":
            continue

        text = p["text"]
        start = time.perf_counter()
        clean, findings = redactor.scan(text)
        elapsed_ms = (time.perf_counter() - start) * 1000

        detected = len(findings) > 0
        expected = p.get("expected") == "detected"

        results.append(
            {
                "name": p["name"],
                "scanner": "secret_redactor",
                "detected": detected,
                "expected": expected,
                "correct": detected == expected,
                "finding_count": len(findings),
                "findings": [f.pattern_name for f in findings],
                "latency_ms": elapsed_ms,
            }
        )

    return results


def eval_ssrf_validator(payloads: list[dict]) -> list[dict]:
    validator = SSRFValidator()
    results = []

    for p in payloads:
        if p.get("scanner") != "ssrf_validator":
            continue

        urls = p.get("urls", [])
        all_blocked = True
        url_results = []

        start = time.perf_counter()
        for url in urls:
            result = validator.validate_url(url, resolve_dns=False)
            url_results.append({"url": url, "safe": result.safe, "reason": result.reason})
            if result.safe:
                all_blocked = False
        elapsed_ms = (time.perf_counter() - start) * 1000

        expected = p.get("expected") == "blocked"

        # Also test redirect chain if present
        chain = p.get("redirect_chain", [])
        chain_result = None
        if chain:
            cr = validator.validate_redirect_chain(chain)
            chain_result = {"safe": cr.safe, "reason": cr.reason}
            if cr.safe:
                all_blocked = False

        results.append(
            {
                "name": p["name"],
                "scanner": "ssrf_validator",
                "detected": all_blocked,
                "expected": expected,
                "correct": all_blocked == expected,
                "url_results": url_results,
                "chain_result": chain_result,
                "latency_ms": elapsed_ms,
            }
        )

    return results


def eval_context_injection(payloads: list[dict]) -> list[dict]:
    scanner = ContextInjectionScanner()
    results = []

    for p in payloads:
        if p.get("scanner") != "context_injection":
            continue

        content = p["content"]
        filename = p.get("filename", "")

        start = time.perf_counter()
        result = scanner.scan(content, filename)
        elapsed_ms = (time.perf_counter() - start) * 1000

        detected = not result.safe
        expected = p.get("expected") == "blocked"

        results.append(
            {
                "name": p["name"],
                "scanner": "context_injection",
                "detected": detected,
                "expected": expected,
                "correct": detected == expected,
                "finding_count": len(result.findings),
                "findings": [
                    {"pattern": f.pattern_name, "severity": f.severity, "category": f.category}
                    for f in result.findings
                ],
                "latency_ms": elapsed_ms,
            }
        )

    return results


def eval_unicode_normalizer(payloads: list[dict]) -> list[dict]:
    normalizer = UnicodeNormalizer()
    results = []

    for p in payloads:
        if p.get("scanner") != "unicode_normalizer":
            continue

        text = p["text"]
        expected_clean = p.get("clean_text", "")

        start = time.perf_counter()
        result = normalizer.normalize(text)
        elapsed_ms = (time.perf_counter() - start) * 1000

        detected = result.changed
        expected = p.get("expected") == "normalized"
        correct_output = result.normalized == expected_clean if expected_clean else True

        results.append(
            {
                "name": p["name"],
                "scanner": "unicode_normalizer",
                "detected": detected,
                "expected": expected,
                "correct": detected == expected,
                "correct_output": correct_output,
                "normalized": result.normalized,
                "expected_clean": expected_clean,
                "findings": [
                    {"category": f.category, "count": f.count, "description": f.description}
                    for f in result.findings
                ],
                "latency_ms": elapsed_ms,
            }
        )

    return results


def print_results(all_results: list[dict]):
    print(f"\n{'=' * 100}")
    print("  HERMES SECURITY PATTERNS EVALUATION")
    print(f"{'=' * 100}")

    # Group by scanner
    by_scanner: dict[str, list[dict]] = {}
    for r in all_results:
        by_scanner.setdefault(r["scanner"], []).append(r)

    for scanner, results in sorted(by_scanner.items()):
        print(f"\n--- {scanner} ---")
        for r in results:
            status = "PASS" if r["correct"] else "FAIL"
            det = "DETECTED" if r["detected"] else "CLEAN"
            exp = "expected" if r["correct"] else "UNEXPECTED"
            print(f"  [{status}] {r['name']:<40} {det:<10} ({exp}, {r['latency_ms']:.1f}ms)")

            if r.get("findings"):
                if isinstance(r["findings"][0], str):
                    print(f"         patterns: {', '.join(r['findings'])}")
                elif isinstance(r["findings"][0], dict):
                    for f in r["findings"][:5]:
                        if "pattern" in f:
                            print(f"         [{f['severity']}] {f['pattern']}: {f['category']}")
                        elif "category" in f:
                            print(f"         {f['category']}: {f['description']}")

            if "correct_output" in r and not r["correct_output"]:
                print("         OUTPUT MISMATCH:")
                print(f"           got:      {repr(r['normalized'])}")
                print(f"           expected: {repr(r['expected_clean'])}")

    # Summary
    print(f"\n{'=' * 100}")
    print("  SUMMARY")
    print(f"{'=' * 100}")

    total = len(all_results)
    correct = sum(1 for r in all_results if r["correct"])
    avg_latency = sum(r["latency_ms"] for r in all_results) / total if total else 0

    print(f"\n  Total payloads:  {total}")
    print(f"  Correct:         {correct}/{total} ({100 * correct / total:.0f}%)")
    print(f"  Avg latency:     {avg_latency:.1f}ms")

    for scanner, results in sorted(by_scanner.items()):
        n = len(results)
        c = sum(1 for r in results if r["correct"])
        avg = sum(r["latency_ms"] for r in results) / n if n else 0
        print(f"\n  {scanner}:")
        print(f"    Correct: {c}/{n} ({100 * c / n:.0f}%)")
        print(f"    Avg latency: {avg:.1f}ms")

    if correct < total:
        print("\n  FAILURES:")
        for r in all_results:
            if not r["correct"]:
                print(f"    - {r['name']} ({r['scanner']})")


def main():
    payloads = load_payloads()
    print(f"Loaded {len(payloads)} payloads from {PAYLOADS_DIR}")

    all_results = []
    all_results.extend(eval_secret_redactor(payloads))
    all_results.extend(eval_ssrf_validator(payloads))
    all_results.extend(eval_context_injection(payloads))
    all_results.extend(eval_unicode_normalizer(payloads))

    print_results(all_results)

    # Exit with failure if any test is wrong
    if not all(r["correct"] for r in all_results):
        sys.exit(1)


if __name__ == "__main__":
    main()
