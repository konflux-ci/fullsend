from dataclasses import dataclass

from scanner.config import ScannerConfig
from scanner.parser import TektonTask


@dataclass
class Violation:
    task_name: str
    task_file: str
    step_name: str
    current_image: str


def detect_drift(task: TektonTask, config: ScannerConfig) -> list[Violation]:
    violations = []
    for step in task.steps:
        if step.image_repo == config.task_runner_image:
            continue
        if step.image_repo in config.exempt_images:
            continue
        violations.append(
            Violation(
                task_name=task.name,
                task_file=str(task.file_path),
                step_name=step.name,
                current_image=step.image_repo,
            )
        )
    return violations
