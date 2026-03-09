from pathlib import Path

from scanner.config import ScannerConfig
from scanner.detector import Violation, detect_drift
from scanner.parser import parse_task


def scan_directory(root: Path, config: ScannerConfig) -> list[Violation]:
    violations = []
    for scan_path in config.scan_paths:
        search_root = root / scan_path
        if not search_root.exists():
            continue
        for yaml_file in search_root.rglob("*.yaml"):
            task = parse_task(yaml_file)
            if task is None:
                continue
            violations.extend(detect_drift(task, config))
    return violations
