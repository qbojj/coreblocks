#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
import os
import subprocess
import tempfile

COREBLOCKS_ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "test" / "regression").is_dir())
if str(COREBLOCKS_ROOT) not in sys.path:
    sys.path.insert(0, str(COREBLOCKS_ROOT))

from test.regression.pysim import PySimulation

from test.regression.arch_elf import run_arch_elf
ARCH_TEST_ROOT = COREBLOCKS_ROOT / "test" / "external" / "riscv-arch-test" / "riscv-arch-test"


def _set_transactron_env_defaults() -> None:
    os.environ.setdefault("__TRANSACTRON_LOG_LEVEL", "WARNING")
    os.environ.setdefault("__TRANSACTRON_LOG_FILTER", ".*")


def _run_pysim(elf_path: Path, timeout_cycles: int) -> int:
    _set_transactron_env_defaults()
    sim = PySimulation()
    return asyncio.run(run_arch_elf(sim, elf_path, timeout_cycles=timeout_cycles))


def _run_cocotb(elf_path: Path, timeout_cycles: int, traces: bool) -> int:
    _set_transactron_env_defaults()
    with tempfile.TemporaryDirectory(prefix="coreblocks-arch-elf-") as temp_dir:
        env = dict(os.environ)
        env["TESTNAME"] = str(elf_path)
        env["VERILOG_SOURCES"] = str(COREBLOCKS_ROOT / "core.v")
        env["_COREBLOCKS_GEN_INFO"] = str(COREBLOCKS_ROOT / "core.v.json")
        env["SIM_BUILD"] = str()
        env["COCOTB_RESULTS_FILE"] = str(Path(temp_dir) / "results.xml")
        env["SIM_BUILD"] = str(COREBLOCKS_ROOT / "cocotb" / "build" / "arch_elf")
        if traces:
            env["TRACES"] = "1"

        command = [
            "make",
            "-C",
            str(COREBLOCKS_ROOT / "test" / "regression" / "cocotb"),
            "-f",
            "arch_elf.Makefile",
            f"VERILOG_SOURCES={env['VERILOG_SOURCES']}",
            f"_COREBLOCKS_GEN_INFO={env['_COREBLOCKS_GEN_INFO']}",
            f"COCOTB_RESULTS_FILE={env['COCOTB_RESULTS_FILE']}",
            f"SIM_BUILD={env['SIM_BUILD']}",
            f"TESTNAME={elf_path}",
        ]
        if traces:
            command.append("TRACES=1")

        result = subprocess.run(command, cwd=ARCH_TEST_ROOT, env=env)
        return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a single Coreblocks arch-test ELF")
    parser.add_argument("elf_path", type=Path, help="Path to the ELF file to execute")
    parser.add_argument("--backend", choices=["pysim", "cocotb"], default="pysim", help="Simulation backend")
    parser.add_argument("--timeout-cycles", type=int, default=2_000_000, help="Maximum simulated cycles")
    parser.add_argument("--traces", action="store_true", help="Enable cocotb trace generation")
    args = parser.parse_args()

    if not args.elf_path.is_file():
        parser.error(f"ELF file not found: {args.elf_path}")

    if args.backend == "pysim":
        return _run_pysim(args.elf_path.resolve(), args.timeout_cycles)

    return _run_cocotb(args.elf_path.resolve(), args.timeout_cycles, args.traces)


if __name__ == "__main__":
    raise SystemExit(main())
