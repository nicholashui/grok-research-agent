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
    start.add_argument(
        "--mode",
        dest="session_mode",
        default="report",
        choices=["report", "compiler", "drill"],
    )

    resume = sub.add_parser("resume", help="Resume an existing session", parents=[common])
    resume.add_argument("--session-id", required=True)

    ls = sub.add_parser("list-sessions", help="List existing sessions", parents=[common])

    list_types = sub.add_parser("list-types", help="List knowledge abstraction types")

    update = sub.add_parser("update", help="Update an existing session", parents=[common])
    update.add_argument("--session-id", required=True)

    synthesize = sub.add_parser("synthesize", help="Force a synthesis step", parents=[common])
    synthesize.add_argument("--session-id", required=True)

    compile_cmd = sub.add_parser("compile", help="Compile structured knowledge base", parents=[common])
    compile_cmd.add_argument("--session-id", required=True)
    compile_cmd.add_argument(
        "--type",
        dest="compile_type",
        default="auto-hypergraph",
        choices=["auto-hypergraph"],
    )

    drill_cmd = sub.add_parser("drill", help="Generate backward drill pack", parents=[common])
    drill_cmd.add_argument("--session-id", required=True)
    drill_cmd.add_argument(
        "--mode",
        dest="drill_mode",
        default="backward",
        choices=["backward"],
    )

    feed_cmd = sub.add_parser("feed", help="Feed a new document into an existing session", parents=[common])
    feed_cmd.add_argument("--session-id", required=True)
    feed_cmd.add_argument("--new-doc", required=True)

    show_cmd = sub.add_parser("show", help="Generate a Mermaid view of the hypergraph", parents=[common])
    show_cmd.add_argument("--session-id", required=True)

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

    if args.command == "list-types":
        console.print("auto-hypergraph")
        return 0

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
        session = manager.create_session(topic=args.topic, focus=args.focus, mode=args.session_mode)
        console.print(f"Session created: [bold]{session.session_id}[/bold]")
        runner = WorkflowRunner(session_manager=manager, console=console)
        runner.run(session.session_id)
        return 0

    if args.command in {"resume", "update", "synthesize", "generate-images"}:
        session_id = args.session_id
        runner = WorkflowRunner(session_manager=manager, console=console)
        runner.run(session_id, command=args.command)
        return 0

    if args.command == "compile":
        runner = WorkflowRunner(session_manager=manager, console=console)
        runner.run(args.session_id, command="compile", compile_type=args.compile_type)
        return 0

    if args.command == "drill":
        runner = WorkflowRunner(session_manager=manager, console=console)
        runner.run(args.session_id, command="drill", drill_mode=args.drill_mode)
        return 0

    if args.command == "feed":
        runner = WorkflowRunner(session_manager=manager, console=console)
        runner.run(args.session_id, command="feed", new_doc=args.new_doc)
        return 0

    if args.command == "show":
        runner = WorkflowRunner(session_manager=manager, console=console)
        runner.run(args.session_id, command="show")
        return 0

    console.print(f"Unknown command: {args.command}")
    return 2
