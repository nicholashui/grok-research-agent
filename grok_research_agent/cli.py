import argparse
from pathlib import Path

from rich.console import Console

from grok_research_agent.session_manager import SessionManager
from grok_research_agent.workflow_phases import WorkflowRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="grok-research-agent")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--sessions-dir",
        default=str(Path.cwd() / "research_sessions"),
        help="Directory where sessions are stored",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Start a new research session", parents=[common])
    start.add_argument("--topic", required=True)
    start.add_argument("--focus", default=None)

    resume = sub.add_parser("resume", help="Resume an existing session", parents=[common])
    resume.add_argument("--session-id", required=True)

    ls = sub.add_parser("list-sessions", help="List existing sessions", parents=[common])

    update = sub.add_parser("update", help="Update an existing session", parents=[common])
    update.add_argument("--session-id", required=True)

    synthesize = sub.add_parser("synthesize", help="Force a synthesis step", parents=[common])
    synthesize.add_argument("--session-id", required=True)

    gen = sub.add_parser(
        "generate-images",
        help="Generate Grok Imagine prompts from the report",
        parents=[common],
    )
    gen.add_argument("--session-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    console = Console()
    parser = build_parser()
    args = parser.parse_args(argv)

    sessions_dir = Path(args.sessions_dir)
    manager = SessionManager(sessions_dir=sessions_dir)

    if args.command == "list-sessions":
        sessions = manager.list_sessions()
        if not sessions:
            console.print("No sessions found.")
            return 0
        for s in sessions:
            console.print(s)
        return 0

    if args.command == "start":
        session = manager.create_session(topic=args.topic, focus=args.focus)
        console.print(f"Session created: [bold]{session.session_id}[/bold]")
        runner = WorkflowRunner(session_manager=manager, console=console)
        runner.run(session.session_id)
        return 0

    if args.command in {"resume", "update", "synthesize", "generate-images"}:
        session_id = args.session_id
        runner = WorkflowRunner(session_manager=manager, console=console)
        runner.run(session_id, command=args.command)
        return 0

    console.print(f"Unknown command: {args.command}")
    return 2
