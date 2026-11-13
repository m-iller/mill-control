"""Дымовой запуск расчёта из командной строки."""

from __future__ import annotations

import subprocess
import sys

from millrepair.cli import main


def test_version(capsys) -> None:
    assert main(["--version"]) == 0
    assert "millrepair" in capsys.readouterr().out


def test_calc_prints_units(capsys) -> None:
    assert main(["--calc"]) == 0
    output = capsys.readouterr().out
    assert "Футеровка" in output
    assert "Q =" in output
    assert "t_fail" in output


def test_calc_subprocess() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "millrepair", "--calc"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Футеровка" in completed.stdout
    assert "Q =" in completed.stdout
