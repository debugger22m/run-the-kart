#!/usr/bin/env python3
"""
Run The Kart — entry point.

Usage:
  # Start the API server (default)
  python main.py server

  # Run a single orchestration cycle via CLI
  python main.py run --lat 37.7749 --lng -122.4194 --radius 10
"""

import argparse
import asyncio
import json
import logging
import os
import sys

import uvicorn
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_server(args: argparse.Namespace) -> None:
    """Launch the FastAPI server with uvicorn."""
    from src.api.app import create_app  # noqa: import here to keep startup fast

    app = create_app()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


async def cmd_run(args: argparse.Namespace) -> None:
    """Run one orchestration cycle and print the result to stdout."""
    from src.api.state import AppState  # reuse the same seeded fleet

    state = AppState()
    logger.info("Starting single orchestration cycle...")
    result = await state.orchestrator.run_cycle(
        latitude=args.lat,
        longitude=args.lng,
        radius_km=args.radius,
        hours_ahead=args.hours_ahead,
    )
    print(json.dumps(result.to_dict(), indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run-the-kart",
        description="Autonomous food truck fleet manager",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- server ---
    server_p = sub.add_parser("server", help="Start the REST API server")
    server_p.add_argument("--host", default="0.0.0.0")
    server_p.add_argument("--port", type=int, default=8000)

    # --- run ---
    run_p = sub.add_parser("run", help="Run one orchestration cycle (CLI mode)")
    run_p.add_argument("--lat", type=float, required=True, help="Centre latitude")
    run_p.add_argument("--lng", type=float, required=True, help="Centre longitude")
    run_p.add_argument("--radius", type=float, default=10.0, help="Search radius in km")
    run_p.add_argument("--hours-ahead", type=int, default=12, help="Hours into the future to search")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in.")
        sys.exit(1)

    if args.command == "server":
        cmd_server(args)
    elif args.command == "run":
        asyncio.run(cmd_run(args))


if __name__ == "__main__":
    main()
