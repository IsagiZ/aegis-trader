"""
Aegis — Main console dashboard and orchestrator.
Run: python aegis.py
"""
import os
import sys
import time
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box

from config import CORE_ASSETS, SATELLITE_ASSETS
from market_monitor import run_market_scan, MarketSnapshot, TechnicalSnapshot
from broker import get_account, get_positions
from trading_logger import get_open_trades, get_error_patterns, update_portfolio_snapshot
from config import CORE_ALLOCATION, SATELLITE_ALLOCATION

console = Console()


# ── Dashboard Rendering ────────────────────────────────────────

def _trend_icon(trend: str) -> str:
    return {"bull": "[green]▲ BULL[/green]", "bear": "[red]▼ BEAR[/red]", "neutral": "[yellow]→ NEUT[/yellow]"}.get(trend, "?")

def _bias_icon(bias: str) -> str:
    return {"long": "[green]LONG[/green]", "short": "[red]SHORT[/red]", "flat": "[dim]FLAT[/dim]"}.get(bias, "?")

def _rsi_color(rsi: float) -> str:
    if rsi > 70: return f"[red]{rsi}[/red]"
    if rsi < 30: return f"[green]{rsi}[/green]"
    return f"[white]{rsi}[/white]"


def render_dashboard(snapshot: MarketSnapshot, account: dict, positions: list[dict]):
    console.clear()

    # ── Header ────────────────────────────────────────────────
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = f"[bold cyan]AEGIS QUANT TRADER[/bold cyan]  |  [dim]{ts}[/dim]  |  Paper Trading"
    console.print(Panel(header, box=box.DOUBLE_EDGE))

    # ── Kill Switch ────────────────────────────────────────────
    ks = snapshot.kill_switch
    if ks.active:
        console.print(Panel(
            f"[bold red]KILL SWITCH ACTIVE[/bold red]  —  {ks.reason}\n[red]ALL TRADING SUSPENDED. HOLDING CASH.[/red]",
            style="red", box=box.HEAVY
        ))
    else:
        console.print(Panel("[bold green]Kill Switch: CLEAR — Market conditions normal[/bold green]", style="green"))

    # ── Portfolio Summary ──────────────────────────────────────
    equity     = account.get("equity", 0)
    cash       = account.get("cash", 0)
    core_cap   = equity * CORE_ALLOCATION
    sat_cap    = equity * SATELLITE_ALLOCATION

    acc_table = Table(title="Portfolio", box=box.SIMPLE_HEAD, show_header=True)
    acc_table.add_column("Metric", style="cyan")
    acc_table.add_column("Value", justify="right")
    acc_table.add_row("Total Equity",        f"${equity:,.2f}")
    acc_table.add_row("Cash",                f"${cash:,.2f}")
    acc_table.add_row("Core Allocation (90%)", f"${core_cap:,.2f}")
    acc_table.add_row("Satellite BTC (10%)", f"${sat_cap:,.2f}")

    # ── Market Signals ─────────────────────────────────────────
    mkt_table = Table(title="Market Signals", box=box.SIMPLE_HEAD)
    for col in ["Asset", "Price", "Trend", "RSI", "EMA20", "EMA50", "EMA200", "Bias"]:
        mkt_table.add_column(col, justify="right" if col != "Asset" else "left")

    for asset, snap in snapshot.assets.items():
        seg = "[cyan]CORE[/cyan]" if asset in CORE_ASSETS else "[magenta]SAT[/magenta]"
        mkt_table.add_row(
            f"{seg} {asset}",
            f"${snap.price:,.4f}",
            _trend_icon(snap.trend),
            _rsi_color(snap.rsi),
            f"{snap.ema20:,.2f}",
            f"{snap.ema50:,.2f}",
            f"{snap.ema200:,.2f}",
            _bias_icon(snap.bias),
        )

    console.print(Columns([acc_table, mkt_table]))

    # ── Open Positions ─────────────────────────────────────────
    if positions:
        pos_table = Table(title="Open Positions", box=box.SIMPLE_HEAD)
        for col in ["Symbol", "Qty", "Avg Entry", "Market Value", "Unrealized P&L", "Side"]:
            pos_table.add_column(col, justify="right" if col != "Symbol" else "left")
        for p in positions:
            pl_str = f"${p['unrealized_pl']:,.2f}"
            pl_colored = f"[green]{pl_str}[/green]" if p["unrealized_pl"] >= 0 else f"[red]{pl_str}[/red]"
            pos_table.add_row(
                p["symbol"], str(p["qty"]), f"${p['avg_entry']:,.4f}",
                f"${p['market_value']:,.2f}", pl_colored, str(p["side"])
            )
        console.print(pos_table)
    else:
        console.print("[dim]No open positions.[/dim]")

    # ── Error Patterns ─────────────────────────────────────────
    patterns = get_error_patterns()
    if patterns:
        console.print(f"\n[yellow]Active Error Blocks ({len(patterns)}):[/yellow]")
        for ep in patterns:
            console.print(f"  [red]#{ep['id']}[/red] [{ep['asset']} {ep['direction']}] — {ep['description']}")

    # ── Fibonacci Levels (quick reference) ────────────────────
    console.print("\n[bold]Key Fibonacci Retracements:[/bold]")
    for asset, snap in snapshot.assets.items():
        levels = "  ".join([f"{k}: {v}" for k, v in snap.fib_levels.items()])
        console.print(f"  [cyan]{asset}[/cyan]  S={snap.support}  R={snap.resistance}  | Fibs → {levels}")


# ── Main Loop ──────────────────────────────────────────────────

def run(interval_seconds: int = 300):
    console.print("[bold cyan]Aegis initializing...[/bold cyan]")

    while True:
        try:
            console.print("[dim]Scanning market...[/dim]")
            snapshot = run_market_scan()
            account  = get_account()
            positions = get_positions()

            # Update log snapshot
            open_trades = get_open_trades()
            update_portfolio_snapshot(
                equity=account["equity"],
                core=account["equity"] * CORE_ALLOCATION,
                satellite=account["equity"] * SATELLITE_ALLOCATION,
                cash=account["cash"],
                open_positions=[p["symbol"] for p in positions],
            )

            render_dashboard(snapshot, account, positions)

            console.print(f"\n[dim]Next scan in {interval_seconds}s. Press Ctrl+C to exit.[/dim]")
            time.sleep(interval_seconds)

        except KeyboardInterrupt:
            console.print("\n[yellow]Aegis halted by user.[/yellow]")
            sys.exit(0)
        except Exception as e:
            console.print(f"[red]ERROR: {e}[/red]")
            time.sleep(30)


if __name__ == "__main__":
    run(interval_seconds=300)
