import sys
from typing import Optional, List, Any
from gemini_webapi.types.image import GeneratedImage, WebImage

# ANSI color codes for fallback formatting
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
RED = "\033[31m"
RESET = "\033[0m"

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.text import Text
    from rich.syntax import Syntax
    from rich.theme import Theme
    from rich.live import Live
    from rich.rule import Rule

    custom_theme = Theme({
        "info": "dim cyan",
        "warning": "yellow",
        "error": "bold red",
        "user": "bold green",
        "assistant": "bold magenta",
        "thought": "italic dim",
    })
    console = Console(theme=custom_theme)
    HAS_RICH = True
except ImportError:
    console = None
    HAS_RICH = False


def print_banner():
    if HAS_RICH and console:
        console.print("\n[bold cyan]✨ Gemini CLI[/bold cyan] [dim]• An intelligent assistant for your terminal[/dim]")
    else:
        print(f"\n{BOLD}{CYAN}✨ Gemini CLI{RESET} {DIM}• An intelligent assistant for your terminal{RESET}")


def print_user_prompt(text: str):
    """Render user prompt with high visual prominence and clear framing."""
    if not text:
        return
    if HAS_RICH and console and sys.stdout.isatty():
        console.print(
            Panel(
                f"[bold bright_white]{text.strip()}[/bold bright_white]",
                title="[bold black on #38bdf8] YOU [/bold black on #38bdf8]",
                title_align="left",
                border_style="#0284c7",
                padding=(0, 2),
                expand=False,
            )
        )
    else:
        print(f"{BOLD}{CYAN}┌── YOU ──────────────────────────────────────────{RESET}")
        print(f"{BOLD}{CYAN}│{RESET} {BOLD}{text.strip()}{RESET}")
        print(f"{BOLD}{CYAN}└────────────────────────────────────────────────{RESET}")


def print_assistant_header(model_name: Optional[str] = None):
    """Render Gemini assistant header with clear spacing."""
    suffix = f" [dim]({model_name})[/dim]" if model_name else ""
    if HAS_RICH and console and sys.stdout.isatty():
        console.print(f"[bold bright_magenta]✨ Gemini[/bold bright_magenta]{suffix}:")
    else:
        suffix_str = f" {DIM}({model_name}){RESET}" if model_name else ""
        print(f"{BOLD}{MAGENTA}✨ Gemini{RESET}{suffix_str}:")


def print_markdown(text: str):
    """Render full markdown text with rich styling (syntax highlighting, tables, lists)."""
    if not text:
        return
    if HAS_RICH and console and sys.stdout.isatty():
        console.print(Markdown(text, code_theme="monokai"))
    else:
        print(text)


class MarkdownStreamer:
    """
    Real-time streamer that transforms and renders Markdown live in the terminal.
    Falls back to raw token printing when piping (not a TTY) or if raw mode is requested.
    """

    def __init__(self, raw: bool = False):
        self.raw = raw or not sys.stdout.isatty() or not HAS_RICH
        self.buffer = ""
        self.live = None

    def __enter__(self):
        if not self.raw and console:
            self.live = Live(
                Markdown("", code_theme="monokai"),
                console=console,
                refresh_per_second=12,
                auto_refresh=False,
                transient=False,
            )
            self.live.__enter__()
        return self

    def update(self, delta: str):
        if not delta:
            return
        self.buffer += delta
        if self.raw:
            print(delta, end="", flush=True)
        elif self.live:
            self.live.update(Markdown(self.buffer, code_theme="monokai"), refresh=True)

    def finish(self):
        if self.raw:
            print()
        elif self.live:
            self.live.update(Markdown(self.buffer, code_theme="monokai"), refresh=True)
            self.live.__exit__(None, None, None)
            self.live = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.live:
            self.live.__exit__(exc_type, exc_val, exc_tb)
            self.live = None


def print_thoughts(thoughts: Optional[str]):
    if not thoughts or not thoughts.strip():
        return
    if HAS_RICH and console:
        console.print(Panel(thoughts.strip(), title="[dim]Thought Process[/dim]", border_style="dim", expand=False))
    else:
        print(f"\n{DIM}{ITALIC}--- Thought Process ---\n{thoughts.strip()}\n-----------------------{RESET}\n")


def print_images(images: Optional[List[Any]]):
    if not images:
        return
    web = [i for i in images if isinstance(i, WebImage)]
    gen = [i for i in images if isinstance(i, GeneratedImage)]

    if HAS_RICH and console:
        if gen:
            console.print("\n[bold magenta]🖼️  Generated Images:[/bold magenta]")
            for img in gen:
                console.print(f"  • [cyan]{img.url}[/cyan]")
        if web:
            console.print("\n[bold blue]🌐 Web Images:[/bold blue]")
            for img in web:
                title = f" - {img.title}" if getattr(img, "title", None) else ""
                console.print(f"  • [cyan]{img.url}[/cyan]{title}")
    else:
        if gen:
            print(f"\n{BOLD}{MAGENTA}🖼️  Generated Images:{RESET}")
            for img in gen:
                print(f"  • {img.url}")
        if web:
            print(f"\n{BOLD}{BLUE}🌐 Web Images:{RESET}")
            for img in web:
                title = f" - {img.title}" if getattr(img, "title", None) else ""
                print(f"  • {img.url}{title}")


def print_chat_metadata(cid: Optional[str]):
    if not cid:
        return
    if HAS_RICH and console:
        console.print(f"\n[dim]Chat ID: {cid}[/dim]")
    else:
        print(f"\n{DIM}Chat ID: {cid}{RESET}")


def print_turn_divider():
    """Print subtle divider between conversation turns."""
    if HAS_RICH and console and sys.stdout.isatty():
        console.print("\n" + "[dim]" + "─" * 60 + "[/dim]\n")
    else:
        print(f"\n{DIM}------------------------------------------------------------{RESET}\n")
