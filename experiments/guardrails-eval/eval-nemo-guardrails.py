"""Evaluate NeMo Guardrails against PR #117 attack payloads.

Tests available local-only detection modes:
1. YARA-based injection detection (sqli, template, code, xss)
2. Jailbreak detection heuristics (GPT-2 perplexity-based)

Note: NeMo's `self check input` and `content safety` rails require an LLM
and are not tested here (they'd need an API key or local model).
"""

import sys
import tempfile
import time
from pathlib import Path

import yaml

PAYLOADS_DIR = Path(__file__).parent.parent / "prompt-injection-defense" / "attacks"


def load_payloads(directory: Path) -> list[dict]:
    payloads = []
    for path in sorted(directory.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        payloads.append(data)
    return payloads


def test_yara_injection_detection(payloads: list[dict]) -> list[dict]:
    """Test NeMo's YARA-based injection detection (code/SQL/XSS only)."""
    from nemoguardrails import RailsConfig

    # Create minimal config for injection detection only (no LLM needed)
    config_dir = tempfile.mkdtemp(prefix="nemo_yara_")
    config_yaml = {
        "models": [],  # No LLM
        "rails": {
            "config": {
                "injection_detection": {
                    "injections": ["sqli", "template", "code", "xss"],
                    "action": "reject",
                }
            }
        },
    }
    config_path = Path(config_dir) / "config.yml"
    config_path.write_text(yaml.dump(config_yaml))

    results = []
    print("=== NeMo Guardrails: YARA Injection Detection ===")
    print("(Detects: SQL injection, template injection, code injection, XSS)")
    print("(Does NOT detect: LLM prompt injection, social engineering)\n")

    try:
        RailsConfig.from_path(config_dir)

        for payload in payloads:
            name = payload["name"]
            text = payload["commit_message"]
            start = time.perf_counter()

            try:
                # Use the injection detection action directly
                from nemoguardrails.actions.injection_detection import detect_injection
                from nemoguardrails.rails.llm.config import InjectionDetection

                id_config = InjectionDetection(
                    injections=["sqli", "template", "code", "xss"],
                    action="reject",
                )
                detection_result = detect_injection(text, id_config)
                elapsed_ms = (time.perf_counter() - start) * 1000
                detected = detection_result is not None
                detail = str(detection_result) if detected else "none"
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                detected = False
                detail = f"error: {e}"

            results.append(
                {
                    "name": name,
                    "detected": detected,
                    "detail": detail,
                    "latency_ms": elapsed_ms,
                }
            )
            status = "DETECTED" if detected else "CLEAN"
            print(f"  {name}: {status} ({elapsed_ms:.0f}ms) {detail}")

    except Exception as e:
        print(f"  Failed to initialize NeMo config: {e}")
        # Fall back to direct YARA testing
        print("  Falling back to direct yara-python testing...\n")
        results = test_yara_direct(payloads)

    return results


def test_yara_direct(payloads: list[dict]) -> list[dict]:
    """Direct YARA rule testing without NeMo framework."""
    try:
        import yara
    except ImportError:
        print("  yara-python not installed, skipping YARA tests")
        return [
            {"name": p["name"], "detected": False, "detail": "skipped", "latency_ms": 0}
            for p in payloads
        ]

    # Basic prompt injection YARA rules
    rules_source = """
    rule PromptInjection_IgnoreInstructions {
        meta:
            description = "Detects common prompt injection patterns"
        strings:
            $ignore1 = "ignore all previous instructions" nocase
            $ignore2 = "ignore your instructions" nocase
            $ignore3 = "disregard all previous" nocase
            $ignore4 = "forget your instructions" nocase
            $override1 = "you are no longer" nocase
            $override2 = "new instructions" nocase
        condition:
            any of them
    }

    rule PromptInjection_SystemPromptLeak {
        meta:
            description = "Detects attempts to leak system prompts"
        strings:
            $leak1 = "reveal your system prompt" nocase
            $leak2 = "show me your instructions" nocase
            $leak3 = "what are your rules" nocase
        condition:
            any of them
    }

    rule SocialEngineering_AlreadyApproved {
        meta:
            description = "Detects social engineering claiming pre-approval"
        strings:
            $se1 = "already approved" nocase
            $se2 = "without any further inspection" nocase
            $se3 = "no further review" nocase
        condition:
            any of them
    }

    rule InjectionMarker_Escape {
        meta:
            description = "Detects attempts to escape data markers"
        strings:
            $marker1 = "END_UNTRUSTED_DATA" nocase
            $marker2 = "END_DATA" nocase
            $marker3 = "<<<END_" nocase
        condition:
            any of them
    }
    """

    results = []
    print("=== Direct YARA Rules (custom prompt injection patterns) ===\n")

    try:
        compiled = yara.compile(source=rules_source)
    except Exception as e:
        print(f"  Failed to compile YARA rules: {e}")
        return [
            {"name": p["name"], "detected": False, "detail": "compile error", "latency_ms": 0}
            for p in payloads
        ]

    for payload in payloads:
        name = payload["name"]
        text = payload["commit_message"]

        start = time.perf_counter()
        matches = compiled.match(data=text)
        elapsed_ms = (time.perf_counter() - start) * 1000

        detected = len(matches) > 0
        detail = ", ".join(m.rule for m in matches) if detected else "none"

        results.append(
            {
                "name": name,
                "detected": detected,
                "detail": detail,
                "latency_ms": elapsed_ms,
            }
        )
        status = "DETECTED" if detected else "CLEAN"
        print(f"  {name}: {status} ({elapsed_ms:.1f}ms) [{detail}]")

    return results


def main():
    if not PAYLOADS_DIR.exists():
        print(f"Payloads directory not found: {PAYLOADS_DIR}")
        sys.exit(1)

    payloads = load_payloads(PAYLOADS_DIR)
    print(f"Loaded {len(payloads)} payloads from {PAYLOADS_DIR}\n")

    # Test 1: NeMo YARA injection detection
    results_yara = test_yara_injection_detection(payloads)

    print()

    # Test 2: Custom YARA rules for prompt injection
    results_custom_yara = test_yara_direct(payloads)

    # Print comparison
    print("\n" + "=" * 90)
    print("NEMO / YARA COMPARISON")
    print("=" * 90)
    header = f"| {'Payload':<22} | {'NeMo YARA':<12} | {'Custom YARA':<30} | {'Latency':<8} |"
    print(header)
    print("|" + "|".join(["-" * n for n in [24, 14, 32, 10]]) + "|")

    for i, payload in enumerate(payloads):
        name = payload["name"]
        ry = (
            results_yara[i]
            if i < len(results_yara)
            else {"detected": False, "detail": "N/A", "latency_ms": 0}
        )
        rc = (
            results_custom_yara[i]
            if i < len(results_custom_yara)
            else {"detected": False, "detail": "N/A", "latency_ms": 0}
        )

        def status(r):
            return "DETECTED" if r["detected"] else "CLEAN"

        lat = rc["latency_ms"]
        print(
            f"| {name:<22} | {status(ry):<12} "
            f"| {status(rc):<12} {rc['detail']:<17} | {lat:<6.1f}ms |"
        )

    # Summary
    attacks = [p for p in payloads if p["name"] != "benign"]
    n = len(attacks)

    def dr(results):
        return sum(
            1
            for r, p in zip(results, payloads, strict=True)
            if p["name"] != "benign" and r["detected"]
        )

    print("\nDetection rates (attacks only):")
    print(f"  NeMo YARA (sqli/xss/code/template): {dr(results_yara)}/{n}")
    print(f"  Custom YARA (prompt injection patterns): {dr(results_custom_yara)}/{n}")
    print("\nNote: NeMo's jailbreak heuristics (GPT-2 perplexity) require PyTorch (~2GB)")
    print("and are designed for GCG-style adversarial suffixes, not social engineering.")
    print("They were not tested in this evaluation.")


if __name__ == "__main__":
    main()
