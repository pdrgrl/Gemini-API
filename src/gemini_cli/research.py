import asyncio
import sys
from pathlib import Path
from typing import Optional

from gemini_webapi import GeminiClient
from .formatter import BOLD, CYAN, GREEN, DIM, RED, RESET


async def cmd_research_send(client: GeminiClient, prompt: str, model: Optional[str] = None):
    chat = client.start_chat(model=model)
    print(f"{DIM}Planning deep research for:{RESET} {prompt}")
    plan = await client.create_deep_research_plan(prompt, chat=chat)

    print(f"\n{BOLD}{CYAN}Plan:{RESET} {plan.title}")
    if getattr(plan, "eta_text", None):
        print(f"{DIM}Estimated Time:{RESET} {plan.eta_text}")
    print(f"{BOLD}Steps:{RESET}")
    for i, step in enumerate(plan.steps, 1):
        print(f"  {i}. {step}")

    print(f"\n{DIM}Starting research task...{RESET}")
    await client.start_deep_research(plan, chat=chat)

    research_id = plan.research_id if getattr(plan, "research_id", None) else getattr(plan, "id", None)
    print(f"\n{GREEN}✓ Research started successfully!{RESET}")
    print(f"  • Chat ID:     {BOLD}{chat.cid}{RESET}")
    if research_id:
        print(f"  • Research ID: {BOLD}{research_id}{RESET}")

    print(f"\n{DIM}To check progress later:{RESET}")
    if research_id:
        print(f"  gemini research check {chat.cid} --research-id {research_id}")
    else:
        print(f"  gemini research check {chat.cid}")
    print(f"{DIM}To retrieve final report:{RESET}")
    print(f"  gemini research get {chat.cid} -o report.md")


async def cmd_research_check(
    client: GeminiClient, chat_id: str, research_id: Optional[str] = None
):
    print(f"{DIM}Checking research progress for chat {chat_id}...{RESET}")
    try:
        output = await client.fetch_latest_chat_response(chat_id)
        if output and output.deep_research_document:
            doc = output.deep_research_document
            if doc.ready:
                print(f"\n{GREEN}✓ Research is COMPLETE!{RESET}")
                print(f"Title: {BOLD}{doc.title}{RESET}")
                print(f"{DIM}Run 'gemini research get {chat_id} -o report.md' to view the full report.{RESET}")
                return
            else:
                print(f"\n{DIM}Status: Research is in progress...{RESET}")
        else:
            print(f"\n{DIM}Status: Pending / In Progress.{RESET}")
    except Exception as err:
        print(f"{RED}Error checking status: {err}{RESET}")


async def cmd_research_get(
    client: GeminiClient, chat_id: str, output_path: Optional[str] = None
):
    print(f"{DIM}Fetching research document for chat {chat_id}...{RESET}")
    try:
        output = await client.fetch_latest_chat_response(chat_id)
        doc = getattr(output, "deep_research_document", None)
        if not doc or not getattr(doc, "content", None):
            # Fallback to chat history or text
            if output and output.text:
                content = output.text
                title = "Gemini Research Report"
            else:
                print(f"{RED}No research report ready yet for chat {chat_id}.{RESET}")
                return
        else:
            content = getattr(doc, "markdown", getattr(doc, "content", ""))
            title = getattr(doc, "title", "Gemini Research Report")

        if output_path:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            print(f"{GREEN}✓ Report saved to {p.resolve()}{RESET}")
        else:
            print(f"\n# {title}\n\n{content}")
    except Exception as err:
        print(f"{RED}Error fetching report: {err}{RESET}")


async def cmd_research_run(
    client: GeminiClient,
    prompt: str,
    output_path: Optional[str] = None,
    poll_interval: float = 10.0,
    timeout: float = 600.0,
    model: Optional[str] = None,
):
    print(f"{BOLD}{CYAN}🔬 Starting Deep Research:{RESET} {prompt}")
    print(f"{DIM}This process typically takes 3-10 minutes. Polling every {poll_interval}s...{RESET}\n")

    try:
        result = await client.deep_research(
            prompt, poll_interval=poll_interval, timeout=timeout, model=model
        )
        if getattr(result, "done", True):
            print(f"\n{GREEN}✓ Research complete!{RESET}\n")
            doc = getattr(result, "document", None)
            content = (
                getattr(doc, "markdown", getattr(doc, "content", ""))
                if doc
                else getattr(result, "text", "")
            )
            if output_path:
                p = Path(output_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                print(f"{GREEN}Saved report to: {p.resolve()}{RESET}")
            else:
                print(content)
        else:
            print(f"{RED}Research timed out after {timeout} seconds.{RESET}")
    except Exception as err:
        print(f"{RED}Deep research encountered an error: {err}{RESET}")
