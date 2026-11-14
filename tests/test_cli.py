"""Дымовой запуск расчёта и оптимизации из командной строки."""

from __future__ import annotations

import subprocess
import sys

import pytest

from millrepair.cli import main


def test_version(capsys) -> None:
    assert main(["--version"]) == 0
    assert "millrepair" in capsys.readouterr().out


def test_calc_prints_units(capsys, tmp_path) -> None:
    database = tmp_path / "mill.sqlite"
    assert main(["--calc", "--db", str(database)]) == 0
    output = capsys.readouterr().out
    assert "Футеровка" in output
    assert "Q =" in output
    assert "t_fail" in output


def test_calc_subprocess(tmp_path) -> None:
    database = tmp_path / "mill.sqlite"
    completed = subprocess.run(
        [sys.executable, "-m", "millrepair", "--calc", "--db", str(database)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Футеровка" in completed.stdout
    assert "Q =" in completed.stdout


@pytest.mark.slow
def test_optimize_subprocess(tmp_path) -> None:
    database = tmp_path / "mill.sqlite"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "millrepair",
            "--optimize",
            "--db",
            str(database),
            "--maxiter",
            "1",
            "--popsize",
            "2",
            "--seed",
            "1",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "решени" in completed.stdout.lower()
    assert "T =" in completed.stdout
