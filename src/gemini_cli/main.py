import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import List, Optional

from gemini_webapi import GeminiClient, set_log_level
from .auth import discover_cookies, get_client, persist_cookies
from .formatter import (
    BOLD,
    CYAN,
    GREEN,
    DIM,
    RED,
    RESET,
    print_markdown,
    print_user_prompt,
    print_assistant_header,
    print_turn_divider,
)
from .session import (
    get_last_session,
    run_prompt_stream,
    start_interactive_session,
)
from .research import (
    cmd_research_send,
    cmd_research_check,
    cmd_research_get,
    cmd_research_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gemini",
        description="✨ Gemini CLI - Intelligent conversational assistant for your terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  gemini                                 # Start interactive REPL
  gemini "Explain WebSockets"            # Single prompt with live streaming
  gemini -c "Give me code examples"      # Continue the last conversation
  git diff | gemini "Write a commit msg" # Process piped stdin
  gemini -f error.log "Fix this error"   # Attach local file
  gemini models                          # List available models
  gemini research run "AI in 2026"       # Run autonomous deep research
        """,
    )

    # Core execution flags (matching agy/modern AI CLI standards)
    parser.add_argument("prompt", nargs="*", help="Prompt to send to Gemini (omit for interactive session)")
    parser.add_argument("-i", "--prompt-interactive", action="store_true", help="Start interactive session after running initial prompt")
    parser.add_argument("-c", "--continue", dest="continue_last", action="store_true", help="Continue the most recent conversation")
    parser.add_argument("--conversation", dest="conversation_id", help="Resume a specific conversation by ID")
    parser.add_argument("-m", "--model", help="Specify Gemini model (e.g. gemini-pro, gemini-flash)")
    parser.add_argument("-f", "--file", dest="files", action="append", help="Attach a file or image (repeatable)")
    parser.add_argument("--thoughts", action="store_true", help="Display the model's thinking process")
    parser.add_argument("--raw", action="store_true", help="Output raw text without rich markdown formatting")
    parser.add_argument("--no-stream", action="store_true", help="Wait for full response before printing")

    # Auth & Network options
    parser.add_argument("--cookies-json", help="Path to cookies JSON file")
    parser.add_argument("--no-persist", action="store_true", help="Do not write auto-refreshed cookies back")
    parser.add_argument("--proxy", help="HTTP/HTTPS proxy URL")
    parser.add_argument("--account-index", type=int, help="Google account index (default: 0)")
    parser.add_argument("--request-timeout", type=int, default=300, help="Request timeout in seconds (default: 300)")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    # Subcommands
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommands")

    # Subcommand: models
    subparsers.add_parser("models", help="List available Gemini models")

    # Subcommand: list / chats
    subparsers.add_parser("list", help="List recent chat conversations")
    subparsers.add_parser("chats", help="List recent chat conversations")

    # Subcommand: read
    read_p = subparsers.add_parser("read", help="Read full chat transcript")
    read_p.add_argument("chat_id", help="Chat ID to read")

    # Subcommand: research
    research_p = subparsers.add_parser("research", help="Gemini Deep Research")
    research_sub = research_p.add_subparsers(dest="research_subcommand")

    # research run
    r_run = research_sub.add_parser("run", help="Run full deep research end-to-end")
    r_run.add_argument("topic", help="Research topic or prompt")
    r_run.add_argument("-o", "--output", help="Save report to file (e.g. report.md)")
    r_run.add_argument("--timeout", type=float, default=600.0, help="Timeout in seconds")

    # research send
    r_send = research_sub.add_parser("send", help="Start deep research task")
    r_send.add_argument("--prompt", required=True, help="Research prompt")

    # research check
    r_check = research_sub.add_parser("check", help="Check research task status")
    r_check.add_argument("chat_id", help="Chat ID")
    r_check.add_argument("--research-id", help="Optional research task ID")

    # research get
    r_get = research_sub.add_parser("get", help="Retrieve finished research report")
    r_get.add_argument("chat_id", help="Chat ID")
    r_get.add_argument("-o", "--output", help="Save report to file")

    return parser


async def async_main():
    parser = build_parser()
    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        set_log_level("DEBUG")
    else:
        set_log_level("WARNING")

    # Discover and validate cookies
    cookies, cookie_path = discover_cookies(args.cookies_json)
    client = get_client(
        cookies,
        proxy=args.proxy,
        account_index=args.account_index,
    )

    try:
        await client.init(timeout=args.request_timeout, auto_refresh=True)

        # Handle Subcommands
        if args.subcommand in ["models", "model"]:
            models = client.list_models() or []
            print(f"\n{BOLD}Discovered Gemini Models:{RESET}")
            for m in models:
                avail = f"{GREEN}✓ Available{RESET}" if m.is_available else f"{RED}✗ Unavailable{RESET}"
                print(f"  • {BOLD}{m.model_name:<20}{RESET} [{avail}] - {m.display_name}")
            print()
            return

        if args.subcommand in ["list", "chats"]:
            chats = client.list_chats() or []
            print(f"\n{BOLD}Recent Gemini Conversations:{RESET}")
            for c in chats:
                print(f"  • {CYAN}{c.cid:<20}{RESET} {c.title}")
            print()
            return

        if args.subcommand == "read":
            history = await client.read_chat(args.chat_id)
            if history:
                print(f"\n{BOLD}Transcript for {args.chat_id}:{RESET}\n")
                for turn in history.turns:
                    role_color = GREEN if turn.role.lower() == "user" else CYAN
                    print(f"{role_color}{BOLD}[{turn.role.upper()}]{RESET}")
                    if args.raw:
                        print(turn.text)
                    else:
                        print_markdown(turn.text)
                    print()
            else:
                print(f"{RED}No conversation found for ID: {args.chat_id}{RESET}")
            return

        if args.subcommand == "research":
            if args.research_subcommand == "run":
                await cmd_research_run(
                    client, args.topic, output_path=args.output, timeout=args.timeout, model=args.model
                )
            elif args.research_subcommand == "send":
                await cmd_research_send(client, args.prompt, model=args.model)
            elif args.research_subcommand == "check":
                await cmd_research_check(client, args.chat_id, research_id=args.research_id)
            elif args.research_subcommand == "get":
                await cmd_research_get(client, args.chat_id, output_path=args.output)
            else:
                print(f"Usage: gemini research {{run,send,check,get}} ...")
            return

        # Check for piped input on stdin
        piped_input = ""
        if not sys.stdin.isatty():
            try:
                piped_input = sys.stdin.read().strip()
            except Exception:
                pass

        prompt_str = " ".join(args.prompt).strip() if args.prompt else ""
        if piped_input:
            if prompt_str:
                prompt_str = f"{prompt_str}\n\n```\n{piped_input}\n```"
            else:
                prompt_str = piped_input

        # Determine target conversation
        target_cid = args.conversation_id
        if args.continue_last and not target_cid:
            last = get_last_session()
            if last and "last_cid" in last:
                target_cid = last["last_cid"]

        # Interactive REPL mode
        if args.prompt_interactive or (not prompt_str and not piped_input):
            await start_interactive_session(
                client,
                initial_prompt=prompt_str if prompt_str else None,
                resume_cid=target_cid,
                model=args.model,
                show_thoughts=args.thoughts,
                raw=args.raw,
            )
            return

        # Single prompt execution
        if not args.raw:
            print_user_prompt(prompt_str)
            print()
            print_assistant_header(args.model)

        if target_cid:
            latest = await client.fetch_latest_chat_response(target_cid)
            if latest:
                chat = client.start_chat(
                    metadata=list(latest.metadata),
                    cid=target_cid,
                    rcid=latest.rcid,
                    model=args.model,
                )
            else:
                chat = client.start_chat(cid=target_cid, model=args.model)
            await run_prompt_stream(
                client,
                prompt_str,
                chat_session=chat,
                model=args.model,
                files=args.files,
                show_thoughts=args.thoughts,
                raw=args.raw,
            )
        else:
            await run_prompt_stream(
                client,
                prompt_str,
                model=args.model,
                files=args.files,
                show_thoughts=args.thoughts,
                raw=args.raw,
            )

        if not args.raw:
            print_turn_divider()

    finally:
        if cookie_path and not args.no_persist:
            persist_cookies(cookie_path, cookies, client.cookies, verbose=args.verbose)
        await client.close()


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print(f"\n{DIM}Aborted.{RESET}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{BOLD}{RED}Error:{RESET} {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
