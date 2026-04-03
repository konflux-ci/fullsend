"""Evaluate Google Cloud Model Armor against all payloads (original + extended).

Requires env vars: GCP_PROJECT_ID, MODEL_ARMOR_TEMPLATE (and optionally GCP_LOCATION).
Requires: gcloud auth with modelarmor.user role on the target project.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ORIGINAL_DIR = Path(__file__).parent.parent / "prompt-injection-defense" / "attacks"
EXTENDED_DIR = Path(__file__).parent / "payloads"

GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
MODEL_ARMOR_TEMPLATE = os.environ.get("MODEL_ARMOR_TEMPLATE", "")


def get_access_token() -> str:
    gcloud = shutil.which("gcloud")
    if not gcloud:
        print("Error: gcloud CLI not found. Install Google Cloud SDK.", file=sys.stderr)
        sys.exit(1)
    try:
        result = subprocess.run(
            [gcloud, "auth", "print-access-token"],  # noqa: S603
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Error: gcloud auth failed: {e.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def load_payloads(directory: Path) -> list[dict]:
    payloads = []
    for path in sorted(directory.glob("*.yaml")):
        with open(path) as f:
            data = yaml.safe_load(f)
        payloads.append(data)
    return payloads


def scan_with_model_armor(text: str, token: str) -> dict:
    """Call Model Armor sanitizeUserPrompt API."""
    url = (
        f"https://modelarmor.{GCP_LOCATION}.rep.googleapis.com/v1/"
        f"projects/{GCP_PROJECT}/locations/{GCP_LOCATION}/"
        f"templates/{MODEL_ARMOR_TEMPLATE}:sanitizeUserPrompt"
    )

    body = json.dumps({"user_prompt_data": {"text": text}}).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req) as resp:  # nosec B310
            data = json.loads(resp.read())
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"response": data, "latency_ms": elapsed_ms, "error": None}
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"response": None, "latency_ms": elapsed_ms, "error": str(e)}


def parse_result(result: dict) -> tuple[bool, str, str]:
    """Parse Model Armor response into (detected, match_state, details)."""
    if result["error"]:
        return False, "ERROR", result["error"]

    resp = result["response"]
    sanitization = resp.get("sanitizationResult", {})
    match_state = sanitization.get("filterMatchState", "UNKNOWN")

    # Extract filter details
    details = []
    filter_results = sanitization.get("filterResults", {})

    pi_result = filter_results.get("piAndJailbreakFilterResult", {})
    pi_match = pi_result.get("matchState", "UNKNOWN")
    if pi_match == "MATCH_FOUND":
        confidence = pi_result.get("confidenceLevel", "UNKNOWN")
        details.append(f"PI:{confidence}")

    uri_result = filter_results.get("maliciousUriFilterResult", {})
    uri_match = uri_result.get("matchState", "UNKNOWN")
    if uri_match == "MATCH_FOUND":
        details.append("URI:MATCH")

    detected = match_state == "MATCH_FOUND"
    detail_str = ", ".join(details) if details else "none"

    return detected, match_state, detail_str


def main():
    if not GCP_PROJECT:
        print("Error: GCP_PROJECT_ID environment variable is required.", file=sys.stderr)
        sys.exit(1)
    if not MODEL_ARMOR_TEMPLATE:
        print("Error: MODEL_ARMOR_TEMPLATE environment variable is required.", file=sys.stderr)
        sys.exit(1)

    print("Authenticating with GCP...")
    token = get_access_token()
    print(f"Project: {GCP_PROJECT}")
    print(f"Location: {GCP_LOCATION}")
    print(f"Template: {MODEL_ARMOR_TEMPLATE}\n")

    # Load all payloads
    original = load_payloads(ORIGINAL_DIR)
    extended = load_payloads(EXTENDED_DIR)
    all_payloads = original + extended
    print(
        f"Loaded {len(original)} original + {len(extended)} extended = {len(all_payloads)} total\n"
    )

    results = []

    for payload in all_payloads:
        name = payload["name"]
        text = payload["commit_message"]
        technique = payload.get("technique", "original")

        result = scan_with_model_armor(text, token)
        detected, match_state, details = parse_result(result)
        latency = result["latency_ms"]

        results.append(
            {
                "name": name,
                "technique": technique,
                "detected": detected,
                "match_state": match_state,
                "details": details,
                "latency_ms": latency,
                "is_attack": name != "benign",
            }
        )

        status = "BLOCKED" if detected else "CLEAN"
        print(f"  {name:<28} {status:<8} ({match_state}, {details}) {latency:.0f}ms")

    # Summary table
    print(f"\n{'=' * 100}")
    print("MODEL ARMOR RESULTS")
    print(f"{'=' * 100}")
    header = (
        f"| {'Payload':<28} | {'Technique':<18} "
        f"| {'Result':<8} | {'Details':<20} | {'Latency':<8} |"
    )
    print(header)
    print("|" + "|".join(["-" * n for n in [30, 20, 10, 22, 10]]) + "|")

    for r in results:
        status = "BLOCKED" if r["detected"] else "CLEAN"
        lat = r["latency_ms"]
        print(
            f"| {r['name']:<28} | {r['technique']:<18} "
            f"| {status:<8} | {r['details']:<20} | {lat:<6.0f}ms |"
        )

    # Detection rates
    print(f"\n{'=' * 80}")
    print("DETECTION RATES BY CATEGORY")
    print(f"{'=' * 80}")

    categories = {}
    for r in results:
        if not r["is_attack"]:
            continue
        cat = r["technique"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(r["detected"])

    for cat, detections in sorted(categories.items()):
        n = len(detections)
        d = sum(detections)
        print(f"  {cat:<25} {d}/{n} ({100 * d / n:.0f}%)")

    attacks = [r for r in results if r["is_attack"]]
    n = len(attacks)
    d = sum(r["detected"] for r in attacks)
    print(f"\n  {'OVERALL':<25} {d}/{n} ({100 * d / n:.0f}%)")

    # False positives
    benign = [r for r in results if not r["is_attack"]]
    fp = sum(r["detected"] for r in benign)
    print(f"  False positives (benign): {fp}/{len(benign)}")

    avg_latency = sum(r["latency_ms"] for r in results) / len(results)
    print(f"\n  Average latency: {avg_latency:.0f}ms")


if __name__ == "__main__":
    main()
