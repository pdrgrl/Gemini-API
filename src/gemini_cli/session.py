import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional, List

from gemini_webapi import GeminiClient
from .formatter import (
    BOLD,
    CYAN,
    GREEN,
    DIM,
    RESET,
    print_banner,
    print_user_prompt,
    print_assistant_header,
    print_thoughts,
    print_images,
    print_chat_metadata,
    print_markdown,
    MarkdownStreamer,
)

# Optional prompt_toolkit for beautiful interactive line editing and history
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    PromptSession = None
    HAS_PROMPT_TOOLKIT = False

STATE_DIR = Path.home() / ".local" / "state" / "gemini"
STATE_FILE = STATE_DIR / "session_state.json"
HISTORY_FILE = STATE_DIR / "cli_history"


def _ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def save_last_session(cid: str, model_name: Optional[str] = None):
    _ensure_state_dir()
    try:
        STATE_FILE.write_text(
            json.dumps({"last_cid": cid, "model": model_name}), encoding="utf-8"
        )
    except Exception:
        pass


def get_last_session() -> Optional[dict]:
    if STATE_FILE.is_file():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


async def run_prompt_stream(
    client: GeminiClient,
    prompt: str,
    chat_session=None,
    model: Optional[str] = None,
    files: Optional[List[str]] = None,
    show_thoughts: bool = False,
    raw: bool = False,
):
    try:
        output = None
        with MarkdownStreamer(raw=raw) as streamer:
            if chat_session:
                async for chunk in chat_session.send_message_stream(prompt, files=files):
                    output = chunk
                    if chunk.text_delta:
                        streamer.update(chunk.text_delta)
            else:
                async for chunk in client.generate_content_stream(prompt, files=files, model=model):
                    output = chunk
                    if chunk.text_delta:
                        streamer.update(chunk.text_delta)
            streamer.finish()

        if output:
            if show_thoughts and getattr(output, "thoughts", None):
                print_thoughts(output.thoughts)
            print_images(getattr(output, "images", None))
            if chat_session:
                save_last_session(chat_session.cid, model)
            elif output.metadata and len(output.metadata) > 0:
                cid = output.metadata[0]
                save_last_session(cid, model)
                print_chat_metadata(cid)
        return output
    except Exception as err:
        print(f"\n{BOLD}\033[31mError:{RESET} {err}")
        return None


async def start_interactive_session(
    client: GeminiClient,
    initial_prompt: Optional[str] = None,
    resume_cid: Optional[str] = None,
    model: Optional[str] = None,
    show_thoughts: bool = False,
    raw: bool = False,
):
    _ensure_state_dir()
    print_banner()
    print(f"{DIM}Commands: /clear, /models, /model <name>, /export <file>, /help, /exit{RESET}\n")

    current_model = model
    chat = None

    if resume_cid:
        try:
            latest = await client.fetch_latest_chat_response(resume_cid)
            if latest:
                chat = client.start_chat(
                    metadata=list(latest.metadata),
                    cid=resume_cid,
                    rcid=latest.rcid,
                    model=current_model,
                )
            else:
                chat = client.start_chat(cid=resume_cid, model=current_model)
            print(f"{DIM}Resumed conversation: {resume_cid}{RESET}\n")
        except Exception:
            chat = client.start_chat(model=current_model)
    else:
        chat = client.start_chat(model=current_model)

    # Initialize prompt_toolkit if available
    pt_session = None
    if HAS_PROMPT_TOOLKIT:
        pt_session = PromptSession(
            history=FileHistory(str(HISTORY_FILE)),
            auto_suggest=AutoSuggestFromHistory(),
        )

    # If an initial prompt was given, execute it first
    if initial_prompt:
        print_user_prompt(initial_prompt)
        print_assistant_header(current_model)
        await run_prompt_stream(client, initial_prompt, chat_session=chat, model=current_model, show_thoughts=show_thoughts, raw=raw)
        print()

    # Main REPL Loop
    while True:
        try:
            if pt_session:
                user_input = await pt_session.prompt_async("> ")
            else:
                user_input = input(f"{BOLD}{GREEN}>{RESET} ")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{DIM}Exiting session.{RESET}")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Handle commands
        if user_input.lower() in ["/exit", "/quit", "exit", "quit"]:
            print(f"{DIM}Goodbye!{RESET}")
            break

        if user_input == "/clear":
            chat = client.start_chat(model=current_model)
            print(f"{DIM}✨ Started fresh conversation.{RESET}\n")
            continue

        if user_input == "/models":
            models = client.list_models() or []
            print(f"\n{BOLD}Available Models on your account:{RESET}")
            for m in models:
                active = f" {CYAN}(active){RESET}" if m.model_name == current_model else ""
                print(f"  • {BOLD}{m.model_name:<20}{RESET} {m.display_name}{active}")
            print()
            continue

        if user_input.startswith("/model ") or user_input.startswith("/switch "):
            target_model_name = user_input.split(maxsplit=1)[1].strip()
            try:
                resolved = client.resolve_model(target_model_name)
                current_model = resolved.model_name
                chat = client.start_chat(model=current_model)
                print(f"{GREEN}✓ Switched model to {BOLD}{resolved.model_name}{RESET} ({resolved.display_name}) and started fresh chat.{RESET}\n")
            except ValueError as err:
                models = client.list_models() or []
                valid_names = ", ".join([m.model_name for m in models])
                print(f"\033[31m✗ Model '{target_model_name}' is not available on your account.{RESET}")
                print(f"  Available models: {BOLD}{valid_names}{RESET}\n")
            continue

        if user_input.startswith("/export "):
            target_path = Path(user_input.split(maxsplit=1)[1].strip())
            try:
                history = await client.read_chat(chat.cid)
                if history:
                    lines = [f"# Chat History ({chat.cid})\n"]
                    for turn in history.turns:
                        lines.append(f"### {turn.role.upper()}\n\n{turn.text}\n")
                    target_path.write_text("\n".join(lines), encoding="utf-8")
                    print(f"{GREEN}Exported conversation to {target_path}{RESET}\n")
                else:
                    print(f"{DIM}No turns found in this chat.{RESET}\n")
            except Exception as err:
                print(f"{RED}Error exporting: {err}{RESET}\n")
            continue

        if user_input == "/help":
            print(f"\n{BOLD}Commands:{RESET}")
            print("  /clear           Start a new clean chat session")
            print("  /models          List available Gemini models on your account")
            print("  /model <name>    Switch model (e.g. /model gemini-flash, /model gemini-pro)")
            print("  /export <file>   Export chat transcript to markdown")
            print("  /exit, /quit     Exit interactive session\n")
            continue

        # Normal prompt execution
        print_assistant_header(current_model)
        await run_prompt_stream(client, user_input, chat_session=chat, model=current_model, show_thoughts=show_thoughts, raw=raw)
        print()

