import pytest
from scanner.config import load_config


def test_load_config_from_file(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """\
task_runner_image: "quay.io/konflux-ci/task-runner"
exempt_images:
  - "quay.io/konflux-ci/build-trusted-artifacts"
scan_paths:
  - "task/"
"""
    )
    config = load_config(str(config_file))
    assert config.task_runner_image == "quay.io/konflux-ci/task-runner"
    assert "quay.io/konflux-ci/build-trusted-artifacts" in config.exempt_images
    assert "task/" in config.scan_paths


def test_load_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")


def test_load_config_missing_required_field(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("exempt_images: []\n")
    with pytest.raises(ValueError, match="task_runner_image"):
        load_config(str(config_file))
