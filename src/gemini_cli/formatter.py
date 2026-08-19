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

    custom_theme = Theme({
        "info": "dim cyan",
        "warning": "yellow",
        "error": "bold red",
        "user": "bold green",
        "assistant": "bold cyan",
        "thought": "italic dim",
    })
    console = Console(theme=custom_theme)
    HAS_RICH = True
except ImportError:
    console = None
    HAS_RICH = False


def print_banner():
    if HAS_RICH and console:
        console.print("[bold cyan]✨ Gemini CLI[/bold cyan] [dim]• An intelligent assistant for your terminal[/dim]")
    else:
        print(f"{BOLD}{CYAN}✨ Gemini CLI{RESET} {DIM}• An intelligent assistant for your terminal{RESET}")


def print_user_prompt(text: str):
    if HAS_RICH and console:
        console.print(f"\n[bold green]You:[/bold green] {text}")
    else:
        print(f"\n{BOLD}{GREEN}You:{RESET} {text}")


def print_assistant_header(model_name: Optional[str] = None):
    suffix = f" [dim]({model_name})[/dim]" if model_name else ""
    if HAS_RICH and console:
        console.print(f"[bold cyan]Gemini[/bold cyan]{suffix}: ", end="")
    else:
        suffix_str = f" {DIM}({model_name}){RESET}" if model_name else ""
        print(f"{BOLD}{CYAN}Gemini{RESET}{suffix_str}: ", end="", flush=True)


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
