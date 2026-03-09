from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ScannerConfig:
    task_runner_image: str
    exempt_images: list[str] = field(default_factory=list)
    scan_paths: list[str] = field(default_factory=lambda: ["task/"])


def load_config(path: str) -> ScannerConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if not data or "task_runner_image" not in data:
        raise ValueError("Config must include 'task_runner_image'")

    return ScannerConfig(
        task_runner_image=data["task_runner_image"],
        exempt_images=data.get("exempt_images", []),
        scan_paths=data.get("scan_paths", ["task/"]),
    )
