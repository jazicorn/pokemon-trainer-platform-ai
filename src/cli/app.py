"""Pokemon Trainer's Second Brain - CLI Application."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import time
from dataclasses import dataclass, field

from agents import evaluate_trade, get_pending_offers, get_trade_suggestions, query_pokedex, send_trade_offer
from agents.trade_market_analyst import query_market
from memory import TradeOffersManager
from data.loader import load_user_collection
from guardrails import create_safe_input
from memory import ConversationMemory, UserPreferencesManager

# Rich imports for high-quality UI and loading indicators
import httpx

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.table import Table

from .commands import CommandType, OfferParams, ParsedCommand, parse_command

_CONFIRMATION_TIMEOUT: float = 300.0  # seconds before a pending confirmation expires


@dataclass
class PendingConfirmation:
    """Tracks a single pending user confirmation with an expiry timestamp."""

    action_type: str  # "accept_offer" | "send_offers"
    offer_id: int | None = None
    timestamp: float = field(default_factory=time.monotonic)

    def is_expired(self) -> bool:
        return time.monotonic() - self.timestamp > _CONFIRMATION_TIMEOUT


# Words that confirm a pending action when typed as the first word of input
_AFFIRMATIONS: frozenset[str] = frozenset({
    "yes", "yeah", "yep", "ok", "okay", "sure", "confirm",
    "go", "proceed", "do",
})

# Initialize Rich console
console = Console(force_terminal=True)

HEADER = """[bold cyan]============================================================
           Pokemon Trainer's Second Brain
============================================================[/bold cyan]
[dim]Your AI-powered trade advisor — type a command or ask in plain English.[/dim]

[bold white]TRADE[/bold white]
  [bold cyan]trade[/]    [italic]{your-pokemon} for {their-pokemon}[/]  [dim]Evaluate a trade[/dim]
  [bold cyan]suggest[/]                                    [dim]Get AI recommendations[/dim]
  [bold cyan]offer[/]    [italic]{pokemon} to {user} for {theirs}[/]    [dim]Send an offer[/dim]
  [bold cyan]offers[/]   [dim]/[/] [bold cyan]offers sent[/]                      [dim]View inbox or sent[/dim]
  [bold cyan]accept[/]   [dim]/[/] [bold cyan]decline[/]  [italic]{offer-id}[/]             [dim]Respond to an offer[/dim]

[bold white]RESEARCH[/bold white]
  [bold cyan]pokedex[/]  [italic]{query}[/]   [dim]Lookup stats, types & abilities[/dim]
  [bold cyan]market[/]   [italic]{query}[/]   [dim]Platform demand & trends[/dim]

[bold white]PROFILE[/bold white]
  [bold cyan]status[/]   [dim]View your trainer status & collection[/dim]
  [bold cyan]prefs[/]    [dim]View your trading goals & preferences[/dim]
  [bold cyan]history[/]  [dim]Recent advisor insights[/dim]

[bold white]APP[/bold white]
  [bold cyan]about[/]  [bold cyan]clear[/]  [bold cyan]help[/]  [bold cyan]quit[/]
[bold cyan]============================================================[/bold cyan]
"""

ABOUT_TEXT = """
# About Pokemon Trainer's Second Brain

This project is a **Hierarchical Multi-Agent System** designed to give you a competitive edge in Pokemon trading.

### How it Works
When you ask a question or propose a trade, the **Trade Advisor** orchestrates the workflow by delegating specialized tasks to worker agents:
* **Pokedex Expert**: Pulls real stats and type data from a ChromaDB vector database.
* **Market Analyst**: Scans platform trades to calculate real-time supply and demand ratios.

### Market Simulation
By analyzing platform-wide trade data, the system simulates a stock market environment, identifying "Bullish" (high demand) and "Bearish" (oversupply) trends based on demand ratios.
"""

class TradeCLI:
    """Command-line interface for the Trade Advisor."""

    def __init__(self, user_id: str = "user_001") -> None:
        """Initialize the CLI."""
        self.user_id = user_id
        self.conversation = ConversationMemory(user_id)
        self.preferences = UserPreferencesManager(user_id)
        self.running = True
        self._pending_confirmation: PendingConfirmation | None = None

    def print_header(self) -> None:
        """Print the application header."""
        console.print(HEADER)

    def print_about(self) -> None:
        """Displays the 'About' information using Rich Markdown."""
        md = Markdown(ABOUT_TEXT)
        console.print(Panel(md, title="[bold green]About the Project[/]", border_style="green", padding=(1, 2)))

    def print_user_context(self) -> None:
        """Displays user stats in a clean, high-quality Rich Table."""
        try:
            collection = load_user_collection(self.user_id)
            owned = len(collection.pokemon)
            goal = collection.preferences.goal
            seeking = ", ".join(collection.preferences.seeking)

            table = Table(show_header=False, box=None, padding=(0, 2), width=60)
            table.add_column("Field", style="dim", width=18)
            table.add_column("Value", style="white")

            table.add_row("[bold white]User ID[/]", f"[cyan]{self.user_id}[/]")
            table.add_row("[bold white]Collection[/]", f"[green]{owned} Pokemon[/]")
            table.add_row("[bold white]Goal[/]", f"[yellow]{goal}[/]")
            table.add_row("[bold white]Seeking[/]", f"[blue]{seeking}[/]")

            console.print("[bold cyan]" + "=" * 60 + "[/]")
            console.print("[bold white]  Current Trainer Status[/]")
            console.print(table)
            console.print("[bold cyan]" + "=" * 60 + "[/]")
            print()
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load user context: {e}[/]\n")

    async def handle_trade(self, cmd: ParsedCommand) -> None:
        """Handle a trade evaluation request with a loading spinner."""
        if not cmd.trade_params:
            console.print("[yellow]💡 Try:[/yellow] trade [italic]{your-pokemon}[/] for [italic]{their-pokemon}[/]")
            return

        offered = cmd.trade_params.offered
        requested = cmd.trade_params.requested

        self.conversation.add_message("user", cmd.args)

        with console.status(f"[bold green]Analyzing trade: {offered} for {requested}...", spinner="dots"):
            result = await evaluate_trade(offered, requested, self.user_id)

        self._print_result(result)
        self.conversation.add_message("assistant", str(result))

    async def handle_suggest(self) -> None:
        """Handle trade suggestions request with a loading spinner."""
        self.conversation.add_message("user", "What trades should I consider?")
        context = self.conversation.get_context_string()
        with console.status("[bold green]Searching for trade opportunities...", spinner="dots"):
            result = await get_trade_suggestions(self.user_id, conversation_context=context)

        self._print_result(result)
        self.conversation.add_message("assistant", str(result))

    async def handle_pokedex(self, query: str) -> None:
        """Handle Pokedex queries with a loading spinner."""
        if not query:
            raw = Prompt.ask("[bold cyan]What would you like to know?[/]")
            processed = create_safe_input(raw)
            if processed.had_pii:
                console.print(f"[yellow]Note: {processed.warning}[/]")
            query = processed.text

        self.conversation.add_message("user", f"Pokedex: {query}")

        with console.status(f"[bold cyan]Querying Pokedex for '{query}'...", spinner="dots"):
            result = await query_pokedex(query)

        self._print_result(result)
        self.conversation.add_message("assistant", str(result))

    async def handle_offers(self, args: str) -> None:
        """Handle inbox or sent-offers view."""
        if args.strip().lower() == "sent":
            mgr = TradeOffersManager(self.user_id)
            sent = mgr.get_sent()
            if not sent:
                self._print_result("You haven't sent any trade offers yet.")
                return
            lines = [f"**{len(sent)} sent offer(s):**\n"]
            for o in sent:
                status_color = {"accepted": "✅", "declined": "❌", "pending": "⏳"}.get(o["status"], "•")
                lines.append(
                    f"{status_color} **Offer #{o['id']}** to `{o['recipient_id']}` — "
                    f"your {o['offered_pokemon']} for their {o['requested_pokemon']} "
                    f"[{o['status']}]"
                )
            self._print_result("\n".join(lines))
        else:
            self.conversation.add_message("user", "Show my trade offers inbox")
            with console.status("[bold green]Fetching your trade offers...", spinner="dots"):
                result = await get_pending_offers(self.user_id)
            self._print_result(result)
            self.conversation.add_message("assistant", str(result))

    async def handle_offer_send(self, params: OfferParams | None) -> None:
        """Pre-screen and send a trade offer."""
        if not params:
            console.print("[yellow]💡 Try:[/yellow] offer [italic]{your-pokemon}[/] to [italic]{user}[/] for [italic]{their-pokemon}[/]")
            return

        self.conversation.add_message(
            "user",
            f"Send offer: {params.offered} to {params.recipient} for {params.requested}",
        )
        with console.status(
            f"[bold green]Evaluating offer: {params.offered} → {params.recipient}...",
            spinner="dots",
        ):
            result = await send_trade_offer(
                self.user_id, params.recipient, params.offered, params.requested
            )
        self._print_result(result)
        self.conversation.add_message("assistant", str(result))

    async def handle_offer_accept(self, offer_id_str: str) -> None:
        """Accept a pending offer by ID, or all pending offers if 'all' is given."""
        first_word = offer_id_str.strip().split()[0] if offer_id_str.strip() else ""
        if first_word == "all":
            mgr = TradeOffersManager(self.user_id)
            offers = mgr.get_inbox()
            if not offers:
                console.print("[yellow]No pending offers to accept.[/yellow]")
                return
            accepted = [o for o in offers if mgr.update_status(o["id"], "accepted")]
            if accepted:
                console.print(f"[bold green]✓ Accepted {len(accepted)} offer(s):[/bold green]")
                for o in accepted:
                    console.print(f"  Offer #{o['id']} — {o['offered_pokemon']} from {o['sender_id']}")
            return

        try:
            offer_id = int(offer_id_str.strip())
        except ValueError:
            # No ID given — if there's exactly one pending offer, accept it automatically
            mgr = TradeOffersManager(self.user_id)
            inbox = mgr.get_inbox()
            if len(inbox) == 1:
                offer_id = inbox[0]["id"]
            elif not inbox:
                console.print("[yellow]No pending offers to accept.[/yellow]")
                return
            else:
                console.print("[yellow]💡 Try:[/yellow] accept [italic]{offer-id}[/]  or  accept all")
                return

        mgr = TradeOffersManager(self.user_id)
        if mgr.update_status(offer_id, "accepted"):
            self._print_result(f"**Offer #{offer_id} accepted.** Well traded!")
        else:
            console.print(f"[yellow]Offer #{offer_id} wasn't found — it may already have been responded to. Type [bold cyan]offers[/bold cyan] to see pending offers.[/yellow]")

    async def handle_offer_decline(self, offer_id_str: str) -> None:
        """Decline a pending offer by ID."""
        try:
            offer_id = int(offer_id_str.strip())
        except ValueError:
            # No ID given — if there's exactly one pending offer, decline it automatically
            mgr = TradeOffersManager(self.user_id)
            inbox = mgr.get_inbox()
            if len(inbox) == 1:
                offer_id = inbox[0]["id"]
            elif not inbox:
                console.print("[yellow]No pending offers to decline.[/yellow]")
                return
            else:
                console.print("[yellow]💡 Try:[/yellow] decline [italic]{offer-id}[/]")
                return

        mgr = TradeOffersManager(self.user_id)
        if mgr.update_status(offer_id, "declined"):
            self._print_result(f"**Offer #{offer_id} declined.**")
        else:
            console.print(f"[yellow]Offer #{offer_id} wasn't found — it may already have been responded to. Type [bold cyan]offers[/bold cyan] to see pending offers.[/yellow]")

    async def handle_market(self, query: str) -> None:
        """Handle market queries or general trends report."""
        is_trends = not query.strip() or "trend" in query.lower()
        
        title = "[bold blue]📈 Live Poké-Market Trends[/]" if is_trends else f"[bold yellow]Market Analysis: {query}[/]"
        prompt = "Provide a high-level report on trending Pokemon and current market demand." if is_trends else query
        
        # UPDATED: Using universal 'dots' spinner
        spinner = "dots"

        self.conversation.add_message("user", f"Market Query: {query}")

        with console.status(f"[bold yellow]Accessing trading floor data...", spinner=spinner):
            result = await query_market(prompt)

        print()
        md = Markdown(str(result))
        console.print(Panel(md, title=title, border_style="blue", padding=(1, 2)))
        print()
        
        self.conversation.add_message("assistant", str(result))

    async def handle_prefs(self) -> None:
        """Display user trading preferences."""
        try:
            collection = load_user_collection(self.user_id)
            p = collection.preferences

            table = Table(show_header=False, box=None, padding=(0, 2), width=60)
            table.add_column("Field", style="dim", width=18)
            table.add_column("Value", style="white")

            table.add_row("[bold white]Goal[/]",           f"[yellow]{p.goal or 'Not set'}[/]")
            table.add_row("[bold white]Seeking[/]",        f"[blue]{', '.join(p.seeking) or 'None'}[/]")
            table.add_row("[bold white]Never trade[/]",    f"[red]{', '.join(p.never_trade) or 'None'}[/]")
            table.add_row("[bold white]Fav types[/]",      f"[magenta]{', '.join(p.favorite_types) or 'None'}[/]")
            table.add_row("[bold white]Trading style[/]",  f"[cyan]{p.trading_style or 'Not set'}[/]")

            console.print("[bold cyan]" + "=" * 60 + "[/]")
            console.print("[bold white]  Trading Preferences[/]")
            console.print(table)
            console.print("[bold cyan]" + "=" * 60 + "[/]")
            print()
        except Exception as e:
            console.print(f"[yellow]Could not load preferences: {e}[/yellow]")

    def _print_result(self, result: str) -> None:
        """Print a formatted result using Rich."""
        content = result
        
        print()
        md = Markdown(content)
        console.print(Panel(md, title="[bold blue]Advisor Response[/]", border_style="blue", padding=(1, 2)))
        print()

    async def process_input(self, user_input: str) -> None:
        """Process user input and route to appropriate handler."""
        processed = create_safe_input(user_input)
        if processed.had_pii:
            console.print(f"[yellow]Note: {processed.warning}[/]")
            user_input = processed.text

        cmd = parse_command(user_input)
        await self._dispatch_command(cmd)

    async def _dispatch_command(self, cmd: ParsedCommand) -> None:
        """Dispatch command to appropriate handler."""
        match cmd.command_type:
            case CommandType.QUIT:
                self.running = False
                console.print("[bold cyan]Closing Second Brain. Good luck with your trades![/]")
            case CommandType.HELP:
                self.print_header()
            case CommandType.ABOUT:
                self.print_about()
            case CommandType.CLEAR:
                os.system('cls' if os.name == 'nt' else 'clear')
                self.print_header()
                self.print_user_context()
            case CommandType.HISTORY:
                history = self.conversation.get_history(limit=5)
                if history:
                    console.print("\n[bold]Recent Activity:[/]")
                    for msg in history:
                        role = "[cyan]You[/]" if msg["role"] == "user" else "[blue]Advisor[/]"
                        console.print(f"{role}: {msg['content'][:80]}...")
            case CommandType.TRADE:
                await self.handle_trade(cmd)
            case CommandType.SUGGEST:
                await self.handle_suggest()
            case CommandType.OFFERS:
                await self.handle_offers(cmd.args)
            case CommandType.OFFER_SEND:
                await self.handle_offer_send(cmd.offer_params)
            case CommandType.OFFER_ACCEPT:
                await self.handle_offer_accept(cmd.args)
            case CommandType.OFFER_DECLINE:
                await self.handle_offer_decline(cmd.args)
            case CommandType.POKEDEX:
                await self.handle_pokedex(cmd.args)
            case CommandType.MARKET:
                await self.handle_market(cmd.args)
            case CommandType.STATUS:
                self.print_user_context()
            case CommandType.PREFS:
                await self.handle_prefs()
            case CommandType.UNKNOWN:
                if not cmd.args.strip():
                    return

                first_word = cmd.args.strip().split()[0].lower()

                # Expire stale confirmations before checking them
                if self._pending_confirmation is not None and self._pending_confirmation.is_expired():
                    self._pending_confirmation = None

                # Dispatch pending confirmation if the user is affirming
                if self._pending_confirmation is not None and first_word in _AFFIRMATIONS:
                    conf = self._pending_confirmation
                    self._pending_confirmation = None

                    if conf.action_type == "accept_offer" and conf.offer_id is not None:
                        await self.handle_offer_accept(str(conf.offer_id))
                    elif conf.action_type == "send_offers":
                        self.conversation.add_message("user", cmd.args)
                        context = self.conversation.get_context_string()
                        with console.status("[bold green]Sending offers...", spinner="dots"):
                            from agents.trade_advisor import evaluate_trade
                            result = await evaluate_trade(
                                user_id=self.user_id,
                                raw_query=(
                                    "The user has confirmed. Call create_outgoing_offer for every offer "
                                    "listed in the previous message. Do NOT re-propose or ask for "
                                    "confirmation again — it has already been given."
                                ),
                                conversation_context=context,
                            )
                        self._print_result(result)
                        self.conversation.add_message("assistant", str(result))
                    return

                # Any non-affirmation clears the pending state
                self._pending_confirmation = None

                self.conversation.add_message("user", cmd.args)
                context = self.conversation.get_context_string()

                is_trend_query = any(word in cmd.args.lower() for word in ["trend", "bullish", "bearish", "sentiment"])
                status_msg = "[bold yellow]Consulting Market Analyst..." if is_trend_query else "[bold blue]Thinking..."

                with console.status(status_msg, spinner="dots"):
                    from agents.trade_advisor import evaluate_trade
                    result = await evaluate_trade(user_id=self.user_id, raw_query=cmd.args, conversation_context=context)

                self._print_result(result)
                self.conversation.add_message("assistant", str(result))

                # Detect pending confirmation from the LLM response.
                # Regex matches the exact phrasing mandated in the system prompt,
                # preventing false positives from descriptive text like "you could accept Offer #3".
                accept_match = re.search(
                    r"Shall I go ahead and accept Offer #(\d+)", result, re.IGNORECASE
                )
                if accept_match:
                    self._pending_confirmation = PendingConfirmation(
                        action_type="accept_offer", offer_id=int(accept_match.group(1))
                    )
                elif re.search(r"Shall I send these offers\?", result, re.IGNORECASE):
                    self._pending_confirmation = PendingConfirmation(action_type="send_offers")
            case _:
                pass

    async def run(self) -> None:
        """Run the CLI main loop."""
        self.print_header()

        while self.running:
            try:
                user_input = Prompt.ask("[bold cyan]>[/]")
                await self.process_input(user_input)
            except KeyboardInterrupt:
                break
            except httpx.ConnectError:
                console.print(
                    "[bold red]ChromaDB is unreachable.[/] The vector database isn't running.\n"
                    "  Restart everything:  [bold cyan]make run[/]\n"
                    "  Or fix Colima:       [bold cyan]colima delete && colima start --vm-type qemu[/]"
                )
            except Exception as e:
                console.print(f"[bold red]Error:[/] {e}")

async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Pokemon Trainer's Second Brain")
    parser.add_argument("--user", default="user_001", help="User ID (default: user_001)")
    args = parser.parse_args()
    await TradeCLI(user_id=args.user).run()

if __name__ == "__main__":
    asyncio.run(main())
    