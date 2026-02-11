"""Smoke test for CLI entrypoint."""

import subprocess
import sys


def test_help():
    result = subprocess.run(
        [sys.executable, "-m", "calibra.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "calibra" in result.stdout.lower()


def test_no_args():
    result = subprocess.run(
        [sys.executable, "-m", "calibra.cli"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
