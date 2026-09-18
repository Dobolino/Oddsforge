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
from quantbot.analysis.value import format_edge_pp, format_ev_pct
from quantbot.i18n import DEFAULT_LANGUAGE, t
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


def _lang(value: str | None) -> str:
    """Resolve the UI language: explicit flag, else the configured default."""

    if value:
        return value.lower() if value.lower() in ("de", "en") else DEFAULT_LANGUAGE
    from quantbot.config import get_settings

    return get_settings().language


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


def _fmt_edge(value: float | None) -> str:
    return format_edge_pp(value) if value is not None else "-"


def _fmt_ev(value: float | None) -> str:
    return format_ev_pct(value) if value is not None else "-"


def _build_provider(live: bool, league: League):  # type: ignore[no-untyped-def]
    """Return a data provider using the same credentials as the dashboard."""

    if not live:
        return None  # orchestrator falls back to the dummy provider

    from pathlib import Path

    from quantbot.data.providers import build_live_provider
    from quantbot.local_credentials import resolve_api_keys

    keys = resolve_api_keys()
    if not keys.football or not keys.odds:
        console.print(f"[red]{t('live_keys_missing', _lang(None))}[/red]")
        raise typer.Exit(code=1)

    return build_live_provider(
        football_api_key=keys.football,
        the_odds_api_key=keys.odds,
        leagues=[league],
        cache_dir=Path.home() / ".quantbot" / "cache",
    )


@app.command()
def info(lang: str = typer.Option(None, "--lang", help="UI language: de or en.")) -> None:
    """Show system and model specification."""

    lg = _lang(lang)
    spec = QuantBotOrchestrator().info()
    table = Table(title=f"QuantBot v{__version__}", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    table.add_row(t("info.model", lg), str(spec["model"]))
    table.add_row(t("info.provider", lg), str(spec["provider"]))
    table.add_row(t("info.margin", lg), str(spec["market_method"]))
    table.add_row(t("info.bankroll", lg), str(spec["initial_bankroll"]))
    table.add_row(t("info.autobet", lg), t("info.autobet_value", lg))
    console.print(table)
    console.print(
        Panel(t("guardrails.body", lg), title=t("guardrails.title", lg), border_style="green")
    )


@app.command()
def status(lang: str = typer.Option(None, "--lang", help="UI language: de or en.")) -> None:
    """Alias for info."""

    info(lang=lang)


@app.command()
def predict(
    league: League = typer.Option(League.PREMIER_LEAGUE, help="League to predict."),
    season: str = typer.Option(_DEFAULT_SEASON, help="Season, e.g. 2024-2025."),
    as_of: str = typer.Option(None, "--as-of", help="Prediction date YYYY-MM-DD (UTC)."),
    live: bool = typer.Option(False, "--live", help="Use real data (needs API keys)."),
    lang: str = typer.Option(None, "--lang", help="UI language: de or en."),
) -> None:
    """Show bet signals, Kelly stakes, and rejection reasons."""

    lg = _lang(lang)
    orchestrator = QuantBotOrchestrator(provider=_build_provider(live, league))
    try:
        reports = orchestrator.predict(league, season, _parse_as_of(as_of))
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        if not live:
            console.print(f"[dim]{t('no_demo', lg)}[/dim]")
        raise typer.Exit(code=1) from exc

    table = Table(title=t("sig.title", lg).format(league=league.value, season=season))
    table.add_column(t("col.match", lg), style="cyan")
    table.add_column(t("col.signal", lg), style="magenta")
    table.add_column(t("col.edge", lg), justify="right")
    table.add_column(t("col.ev", lg), justify="right")
    table.add_column(t("col.stake", lg), justify="right")
    table.add_column(t("col.conf", lg), justify="right")
    table.add_column(t("col.reason", lg), style="dim")

    for report in reports:
        signal = report.signal
        match = report.match
        name = f"{match.home_team.name} vs {match.away_team.name}"
        style = "green" if signal.signal is not SignalType.NO_BET else "red"
        table.add_row(
            name,
            f"[{style}]{signal.signal.value}[/{style}]",
            _fmt_edge(signal.edge),
            _fmt_ev(signal.expected_value),
            f"{signal.stake_fraction * 100:.2f}",
            f"{signal.model_confidence:.0f}",
            signal.rationale,
        )

    console.print(table)
    n_bets = sum(1 for r in reports if r.signal.is_bet)
    console.print(t("sig.footer", lg).format(n=len(reports), k=n_bets))


@app.command()
def backtest(
    league: League = typer.Option(League.PREMIER_LEAGUE, help="League to backtest."),
    season: str = typer.Option(_DEFAULT_SEASON, help="Season, e.g. 2024-2025."),
    bankroll: float = typer.Option(1000.0, help="Initial bankroll."),
    live: bool = typer.Option(False, "--live", help="Use real data (needs API keys)."),
    lang: str = typer.Option(None, "--lang", help="UI language: de or en."),
) -> None:
    """Run a walk-forward backtest and show metrics."""

    lg = _lang(lang)
    orchestrator = QuantBotOrchestrator(provider=_build_provider(live, league), initial_bankroll=bankroll)
    try:
        result = orchestrator.run_backtest(league, season)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    m = result.metrics

    table = Table(title=t("bt.title", lg).format(league=league.value, season=season))
    table.add_column(t("col.metric", lg), style="cyan")
    table.add_column(t("col.value", lg), justify="right", style="white")
    table.add_row(t("bt.matches_eval", lg), str(result.n_evaluated))
    table.add_row(t("bt.bets", lg), str(result.n_bets))
    table.add_row(t("bt.no_bets", lg), str(result.n_no_bet))
    table.add_row(t("bt.initial", lg), f"{result.initial_bankroll:.2f}")
    table.add_row(t("bt.final", lg), f"{result.final_bankroll:.2f}")
    table.add_row(t("bt.total_return", lg), f"{m.total_return * 100:.2f}%")
    table.add_row(t("bt.roi", lg), f"{m.roi * 100:.2f}%")
    table.add_row(t("bt.win_rate", lg), f"{m.win_rate * 100:.2f}%")
    table.add_row(t("bt.profit_factor", lg), _fmt(m.profit_factor, 2))
    table.add_row(t("bt.sharpe", lg), _fmt(m.sharpe, 3))
    table.add_row(t("bt.sortino", lg), _fmt(m.sortino, 3))
    table.add_row(t("bt.max_dd", lg), f"{m.max_drawdown * 100:.2f}%")
    table.add_row(t("bt.avg_clv", lg), _fmt(m.avg_clv))
    table.add_row(t("bt.beat_clv", lg), "-" if m.beat_clv_rate is None else f"{m.beat_clv_rate * 100:.2f}%")
    console.print(table)


@app.command("validate")
def validate_cmd(
    league: str = typer.Option("premier_league", help="League id."),
    season: str = typer.Option(_DEFAULT_SEASON, help="Season label."),
    scope: str = typer.Option("live_default", help="Validation scope key."),
    profile: str = typer.Option(
        "demo",
        help="Artifact profile: 'demo' (never unlocks live) or 'live' (requires real data).",
    ),
    min_n: int | None = typer.Option(None, help="Pre-declared min outer-test n (optional)."),
    max_brier: float | None = typer.Option(None, help="Pre-declared max Brier (optional)."),
    save: bool = typer.Option(False, "--save", help="Persist the artifact under MODEL_DIR/validation."),
    live: bool = typer.Option(False, "--live", help="Use live provider (needs API keys)."),
) -> None:
    """Run a chronological train/calib/test validation (does not invent thresholds).

    Without explicit criteria the artifact stays UNVALIDATED. Demo profile never
    unlocks live Kelly sizing. Do not claim calibration from synthetic fixtures.
    """

    from quantbot.analysis.validation import ValidationCriteria
    from quantbot.analysis.validation_run import run_chronological_validation
    from quantbot.models import DixonColesModel
    from quantbot.schemas import League as LeagueEnum

    try:
        lg = LeagueEnum(league)
    except ValueError as exc:
        raise typer.BadParameter(f"unknown league: {league}") from exc
    if profile not in ("live", "demo"):
        raise typer.BadParameter("profile must be live or demo")
    if live and profile == "live":
        console.print(
            "[yellow]Live-profile VALID requires real chronological evidence; "
            "criteria must be fixed before inspecting test metrics.[/yellow]"
        )

    provider = _build_provider(live, lg)
    orch = QuantBotOrchestrator(provider=provider, live=live)
    matches = orch.universe(lg, season)
    criteria = None
    if any(v is not None for v in (min_n, max_brier)):
        criteria = ValidationCriteria(min_n=min_n, max_brier=max_brier)

    try:
        artifact = run_chronological_validation(
            matches,
            DixonColesModel(min_matches=5),
            scope=scope,
            profile=profile,
            criteria=criteria,
            policy=orch.policy,
            save=save,
            notes="cli validate — synthetic/demo must stay profile=demo",
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"status={artifact.status.value}\n"
            f"n_train={artifact.n_train} n_calib={artifact.n_calib} n_test={artifact.n_test}\n"
            f"metrics={artifact.metrics}\n"
            f"pipeline_hash={artifact.pipeline_hash[:12]}…\n"
            f"id={artifact.artifact_id}",
            title=f"Validation [{profile}/{scope}]",
        )
    )
    if artifact.status.value != "valid":
        console.print(
            "[yellow]Sizing stays locked (UNVALIDATED/EXPIRED). "
            "Pass explicit criteria only when justified by prior evidence.[/yellow]"
        )


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
