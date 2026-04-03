"""Evaluate LLM Guard against extended payload set including unicode/encoding,
token-boundary, and indirect injection attacks.

Runs both original PR #117 payloads and new extended payloads through
LLM Guard's PromptInjection scanner in sentence mode (recommended config).
"""

import sys
import time
from pathlib import Path

import yaml
from llm_guard.input_scanners import InvisibleText, PromptInjection
from llm_guard.input_scanners.prompt_injection import MatchType

ORIGINAL_DIR = Path(__file__).parent.parent / "prompt-injection-defense" / "attacks"
EXTENDED_DIR = Path(__file__).parent / "payloads"


def load_payloads(directory: Path) -> list[dict]:
    payloads = []
    for path in sorted(directory.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        payloads.append(data)
    return payloads


def scan_payload(scanner, text: str) -> tuple[bool, float, float]:
    start = time.perf_counter()
    sanitized, is_valid, risk_score = scanner.scan(text)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return not is_valid, risk_score, elapsed_ms


def run_eval(payloads: list[dict], label: str, scanner_full, scanner_sentence, invisible_scanner):
    print(f"\n{'=' * 100}")
    print(f"  {label}")
    print(f"{'=' * 100}")

    results = []
    for payload in payloads:
        name = payload["name"]
        text = payload["commit_message"]
        technique = payload.get("technique", "original")

        det_full, score_full, lat_full = scan_payload(scanner_full, text)
        det_sent, score_sent, lat_sent = scan_payload(scanner_sentence, text)

        # Also run InvisibleText scanner for unicode payloads
        inv_det = False
        inv_detail = ""
        if technique in ("unicode/encoding", "encoding"):
            inv_start = time.perf_counter()
            _, inv_valid, inv_score = invisible_scanner.scan(text)
            inv_elapsed = (time.perf_counter() - inv_start) * 1000
            inv_det = not inv_valid
            inv_detail = (
                f"{'DETECTED' if inv_det else 'CLEAN'} ({inv_score:.2f}, {inv_elapsed:.0f}ms)"
            )

        is_attack = name != "benign"
        results.append(
            {
                "name": name,
                "technique": technique,
                "det_full": det_full,
                "det_sentence": det_sent,
                "score_full": score_full,
                "score_sentence": score_sent,
                "lat_full": lat_full,
                "lat_sentence": lat_sent,
                "invisible": inv_detail,
                "is_attack": is_attack,
            }
        )

        status_f = "DETECTED" if det_full else "CLEAN"
        status_s = "DETECTED" if det_sent else "CLEAN"
        inv_str = f" | InvisibleText: {inv_detail}" if inv_detail else ""
        print(
            f"  {name:<28} full={status_f:<8} sent={status_s:<8} "
            f"score_f={score_full:+.4f} score_s={score_sent:+.4f}{inv_str}"
        )

    return results


def print_summary_table(all_results: list[dict]):
    print(f"\n{'=' * 120}")
    print("FULL COMPARISON TABLE")
    print(f"{'=' * 120}")

    header = (
        f"| {'Payload':<28} | {'Technique':<18} | {'Full Mode':<10} | "
        f"{'Sentence':<10} | {'Score (F)':<10} | {'Score (S)':<10} | "
        f"{'Latency':<8} | {'InvisibleText':<20} |"
    )
    print(header)
    print("|" + "|".join(["-" * n for n in [30, 20, 12, 12, 12, 12, 10, 22]]) + "|")

    for r in all_results:
        sf = "DETECTED" if r["det_full"] else "CLEAN"
        ss = "DETECTED" if r["det_sentence"] else "CLEAN"
        inv = r["invisible"] if r["invisible"] else "N/A"
        print(
            f"| {r['name']:<28} | {r['technique']:<18} | {sf:<10} | "
            f"{ss:<10} | {r['score_full']:+10.4f} | {r['score_sentence']:+10.4f} | "
            f"{r['lat_sentence']:<6.0f}ms | {inv:<20} |"
        )

    # Detection rates by category
    print(f"\n{'=' * 80}")
    print("DETECTION RATES BY CATEGORY")
    print(f"{'=' * 80}")

    categories = {}
    for r in all_results:
        if not r["is_attack"]:
            continue
        cat = r["technique"]
        if cat not in categories:
            categories[cat] = {"full": [], "sentence": []}
        categories[cat]["full"].append(r["det_full"])
        categories[cat]["sentence"].append(r["det_sentence"])

    for cat, data in sorted(categories.items()):
        n = len(data["full"])
        df = sum(data["full"])
        ds = sum(data["sentence"])
        pct_f = 100 * df / n
        pct_s = 100 * ds / n
        print(f"  {cat:<25} full: {df}/{n} ({pct_f:.0f}%)   sentence: {ds}/{n} ({pct_s:.0f}%)")

    # Overall
    attacks = [r for r in all_results if r["is_attack"]]
    n = len(attacks)
    df_total = sum(r["det_full"] for r in attacks)
    ds_total = sum(r["det_sentence"] for r in attacks)
    pct_f = 100 * df_total / n
    pct_s = 100 * ds_total / n
    lbl = "OVERALL"
    print(f"\n  {lbl:<25} full: {df_total}/{n} ({pct_f:.0f}%)")
    print(f"  {'':<25} sentence: {ds_total}/{n} ({pct_s:.0f}%)")

    # False positives
    benign = [r for r in all_results if not r["is_attack"]]
    fp_full = sum(r["det_full"] for r in benign)
    fp_sent = sum(r["det_sentence"] for r in benign)
    nb = len(benign)
    print(f"\n  False positives (benign):  full: {fp_full}/{nb}   sentence: {fp_sent}/{nb}")


def main():
    if not ORIGINAL_DIR.exists():
        print(f"Original payloads not found: {ORIGINAL_DIR}")
        sys.exit(1)
    if not EXTENDED_DIR.exists():
        print(f"Extended payloads not found: {EXTENDED_DIR}")
        sys.exit(1)

    # Initialize scanners
    print("Initializing scanners...")
    scanner_full = PromptInjection(threshold=0.92, match_type=MatchType.FULL, use_onnx=True)
    scanner_sentence = PromptInjection(threshold=0.92, match_type=MatchType.SENTENCE, use_onnx=True)
    invisible_scanner = InvisibleText()

    # Load payloads
    original = load_payloads(ORIGINAL_DIR)
    extended = load_payloads(EXTENDED_DIR)
    print(f"Loaded {len(original)} original + {len(extended)} extended payloads")

    # Run evals
    results_orig = run_eval(
        original, "ORIGINAL PAYLOADS (PR #117)", scanner_full, scanner_sentence, invisible_scanner
    )
    results_ext = run_eval(
        extended,
        "EXTENDED PAYLOADS (unicode/indirect)",
        scanner_full,
        scanner_sentence,
        invisible_scanner,
    )

    # Combined summary
    all_results = results_orig + results_ext
    print_summary_table(all_results)


if __name__ == "__main__":
    main()
