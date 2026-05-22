"""``jakk`` command-line entry point."""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .findings import render_console, write_jsonl
from .library import filter_cases, load_library
from .scanner import ScanConfig, run_scan


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jakk",
        description="Black-box MCP scanner.",
    )
    sub = parser.add_subparsers(dest="surface", required=True)

    mcp_p = sub.add_parser("mcp", help="MCP-protocol scanning")
    mcp_sub = mcp_p.add_subparsers(dest="cmd", required=True)

    scan_p = mcp_sub.add_parser("scan", help="Scan an MCP endpoint with a YAML attack library.")
    scan_p.add_argument("--endpoint", required=True, help="MCP streamable-HTTP endpoint URL.")
    scan_p.add_argument(
        "--library",
        required=True,
        type=Path,
        help="Path to a directory of jakk YAML test files.",
    )
    scan_p.add_argument("--select", help="Run only the test with this id.")
    scan_p.add_argument("--owasp", help="Filter tests by OWASP code (e.g. MCP05).")
    scan_p.add_argument(
        "--jsonl",
        type=Path,
        help="Write findings as JSONL to this path (in addition to console output).",
    )
    scan_p.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Per-call MCP timeout in seconds (default 15).",
    )
    scan_p.add_argument(
        "--exit-nonzero-on-fired",
        action="store_true",
        help="Return exit code 2 if any finding fired (for CI use).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.surface == "mcp" and args.cmd == "scan":
        return _cmd_scan(args)
    parser.error(f"unknown command: {args.surface} {args.cmd}")
    return 2  # unreachable


def _cmd_scan(args: argparse.Namespace) -> int:
    cases = load_library(args.library)
    selected = filter_cases(cases, select=args.select, owasp=args.owasp)
    if not selected:
        print(
            f"No tests matched (library={args.library} select={args.select} owasp={args.owasp})",
            file=sys.stderr,
        )
        return 1

    cfg = ScanConfig(endpoint=args.endpoint, timeout_s=args.timeout)
    findings = asyncio.run(run_scan(selected, cfg))

    render_console(findings, endpoint=args.endpoint)
    if args.jsonl:
        write_jsonl(findings, args.jsonl)

    fired_any = any(f.fired for f in findings)
    if args.exit_nonzero_on_fired and fired_any:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
