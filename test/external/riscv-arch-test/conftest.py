from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

support = importlib.import_module("support")
discover_arch_test_elves = support.discover_arch_test_elves
ensure_arch_test_cocotb_build = support.ensure_arch_test_cocotb_build


def pytest_sessionstart(session: pytest.Session):
    if getattr(session.config, "workerinput", None) is not None:
        return

    if session.config.getoption("coreblocks_backend") != "cocotb":
        return

    ensure_arch_test_cocotb_build()


def pytest_generate_tests(metafunc: pytest.Metafunc):
    if "elf_path" in metafunc.fixturenames:
        metafunc.parametrize("elf_path", discover_arch_test_elves())
