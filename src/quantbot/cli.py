"""QuantBot command-line interface (Typer + Rich).

Commands:
    backtest  Run a walk-forward backtest and show metrics.
    predict   Show bet signals, Kelly stakes, and rejection reasons.
    info      Show system and model specification (alias: status).
"""

from __future__ import annotations

from datetime import datetime, timezone

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from quantbot import __version__
from quantbot.orchestrator import QuantBotOrchestrator
from quantbot.schemas import League, SignalType

app = typer.Typer(
    name="quantbot",
    help="Probabilistic market analysis for sports and prediction markets.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

_DEFAULT_SEASON = "2024-2025"


def _parse_as_of(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise typer.BadParameter("as-of must be YYYY-MM-DD") from exc
    return parsed.replace(tzinfo=timezone.utc)


def _fmt(value: float | None, digits: int = 4) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _build_provider(live: bool, league: League):  # type: ignore[no-untyped-def]
    """Return a data provider. Live needs both API keys in the environment."""

    if not live:
        return None  # orchestrator falls back to the dummy provider

    from pathlib import Path

    from quantbot.config import get_settings
    from quantbot.data.providers import build_live_provider

    settings = get_settings()
    fd = settings.football_data_api_key
    odds = settings.the_odds_api_key
    if fd is None or odds is None:
        console.print(
            "[red]Live mode needs QUANTBOT_FOOTBALL_DATA_API_KEY and "
            "QUANTBOT_THE_ODDS_API_KEY in your environment or .env file.[/red]"
        )
        raise typer.Exit(code=1)

    return build_live_provider(
        football_api_key=fd.get_secret_value(),
        the_odds_api_key=odds.get_secret_value(),
        leagues=[league],
        cache_dir=Path.home() / ".quantbot" / "cache",
    )


@app.command()
def info() -> None:
    """Show system and model specification."""

    spec = QuantBotOrchestrator().info()
    table = Table(title=f"QuantBot v{__version__}", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Model", str(spec["model"]))
    table.add_row("Data provider", str(spec["provider"]))
    table.add_row("Margin method", str(spec["market_method"]))
    table.add_row("Initial bankroll", str(spec["initial_bankroll"]))
    table.add_row("Automated betting", "disabled (decision support only)")
    console.print(table)
    console.print(
        Panel(
            "Guardrails: zero data leakage, no automated betting, "
            "probability over prediction, strict layer separation.",
            title="Guardrails",
            border_style="green",
        )
    )


@app.command()
def status() -> None:
    """Alias for info."""

    info()


@app.command()
def predict(
    league: League = typer.Option(League.PREMIER_LEAGUE, help="League to predict."),
    season: str = typer.Option(_DEFAULT_SEASON, help="Season, e.g. 2024-2025."),
    as_of: str = typer.Option(None, "--as-of", help="Prediction date YYYY-MM-DD (UTC)."),
    live: bool = typer.Option(False, "--live", help="Use real data (needs API keys)."),
) -> None:
    """Show bet signals, Kelly stakes, and rejection reasons."""

    orchestrator = QuantBotOrchestrator(provider=_build_provider(live, league))
    try:
        reports = orchestrator.predict(league, season, _parse_as_of(as_of))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        if not live:
            console.print(
                "[dim]The demo data covers premier_league and bundesliga. "
                "For other leagues use --live with API keys.[/dim]"
            )
        raise typer.Exit(code=1) from exc

    table = Table(title=f"Signals: {league.value} {season}")
    table.add_column("Match", style="cyan")
    table.add_column("Signal", style="magenta")
    table.add_column("Edge", justify="right")
    table.add_column("EV", justify="right")
    table.add_column("Stake %", justify="right")
    table.add_column("Conf", justify="right")
    table.add_column("Reason", style="dim")

    for report in reports:
        signal = report.signal
        match = report.match
        name = f"{match.home_team.name} vs {match.away_team.name}"
        style = "green" if signal.signal is not SignalType.NO_BET else "red"
        table.add_row(
            name,
            f"[{style}]{signal.signal.value}[/{style}]",
            _fmt(signal.edge),
            _fmt(signal.expected_value),
            f"{signal.stake_fraction * 100:.2f}",
            f"{signal.model_confidence:.0f}",
            signal.rationale,
        )

    console.print(table)
    n_bets = sum(1 for r in reports if r.signal.is_bet)
    console.print(f"{len(reports)} matches evaluated, {n_bets} value signals.")


@app.command()
def backtest(
    league: League = typer.Option(League.PREMIER_LEAGUE, help="League to backtest."),
    season: str = typer.Option(_DEFAULT_SEASON, help="Season, e.g. 2024-2025."),
    bankroll: float = typer.Option(1000.0, help="Initial bankroll."),
    live: bool = typer.Option(False, "--live", help="Use real data (needs API keys)."),
) -> None:
    """Run a walk-forward backtest and show metrics."""

    orchestrator = QuantBotOrchestrator(provider=_build_provider(live, league), initial_bankroll=bankroll)
    try:
        result = orchestrator.run_backtest(league, season)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    m = result.metrics

    table = Table(title=f"Backtest: {league.value} {season}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right", style="white")
    table.add_row("Matches evaluated", str(result.n_evaluated))
    table.add_row("Bets placed", str(result.n_bets))
    table.add_row("No-bet decisions", str(result.n_no_bet))
    table.add_row("Initial bankroll", f"{result.initial_bankroll:.2f}")
    table.add_row("Final bankroll", f"{result.final_bankroll:.2f}")
    table.add_row("Total return", f"{m.total_return * 100:.2f}%")
    table.add_row("ROI (yield)", f"{m.roi * 100:.2f}%")
    table.add_row("Win rate", f"{m.win_rate * 100:.2f}%")
    table.add_row("Profit factor", _fmt(m.profit_factor, 2))
    table.add_row("Sharpe", _fmt(m.sharpe, 3))
    table.add_row("Sortino", _fmt(m.sortino, 3))
    table.add_row("Max drawdown", f"{m.max_drawdown * 100:.2f}%")
    table.add_row("Avg CLV", _fmt(m.avg_clv))
    table.add_row("Beat-CLV rate", "-" if m.beat_clv_rate is None else f"{m.beat_clv_rate * 100:.2f}%")
    console.print(table)


@app.command()
def dashboard(
    port: int = typer.Option(8501, help="Port for the Streamlit server."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the command without launching."),
) -> None:
    """Launch the Streamlit dashboard as a subprocess."""

    import subprocess
    import sys

    from quantbot.dashboard import app_path

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path()),
        "--server.port",
        str(port),
    ]
    if dry_run:
        console.print(" ".join(command))
        return
    console.print(f"Starting dashboard on http://localhost:{port} (Ctrl+C to stop)")
    subprocess.run(command, check=True)


def main() -> None:
    """Console-script entry point."""

    app()


if __name__ == "__main__":
    main()
