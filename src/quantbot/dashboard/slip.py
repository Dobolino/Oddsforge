"""Betting-slip helper: combine tips into a theoretical accumulator.

Not for placing bets — only for showing how a multi-leg slip might look,
ranked for win chance or optionally boosted with higher-odds legs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from html import escape
from math import prod

from quantbot.dashboard.ux import plain_signal_label, tip_badge_html, tip_kind_from_label
from quantbot.orchestrator import SignalReport
from quantbot.schemas import MatchOutcome, TotalsSide

# A real accumulator's fair chance is about 1 / combined_odds. When the model
# claims a far higher chance, its probabilities are overconfident or
# uncalibrated (typically early-season sparse data). Above these bounds the
# displayed chance is not trustworthy and is flagged, not shown as fact.
_MAX_PLAUSIBLE_COMBINED_EV = 0.5   # +50% expected value on a combo is impossible
_MAX_PLAUSIBLE_LEG_EDGE = 0.25     # a single leg 25 pts above the market price


@dataclass(frozen=True)
class SlipLeg:
    match_id: str
    match: str
    tip: str
    outcome: MatchOutcome | TotalsSide
    odds: float
    model_prob: float
    edge: float
    role: str  # "core" | "boost"
    league: str = ""
    kickoff_date: str = ""  # YYYY-MM-DD for multi-day slips
    sport: str = ""  # football | basketball


@dataclass(frozen=True)
class BettingSlip:
    legs: tuple[SlipLeg, ...]
    style: str  # "safe" | "boosted"

    @property
    def combined_odds(self) -> float:
        if not self.legs:
            return 1.0
        return prod(leg.odds for leg in self.legs)

    @property
    def combined_prob(self) -> float:
        """Independence assumption — illustrative only."""

        if not self.legs:
            return 0.0
        return prod(leg.model_prob for leg in self.legs)

    @property
    def expected_value(self) -> float:
        return self.combined_prob * self.combined_odds - 1.0

    @property
    def max_leg_edge(self) -> float:
        """Largest gap between a leg's model probability and its market price."""

        if not self.legs:
            return 0.0
        return max(leg.model_prob - (1.0 / leg.odds) for leg in self.legs if leg.odds > 0)

    @property
    def is_plausible(self) -> bool:
        """False when the model's numbers imply an impossible edge.

        Guards against showing an overconfident chance (e.g. 79% on a combo
        paying 16x) as if it were real. Such numbers come from uncalibrated or
        sparse-data probabilities and must be flagged, not presented cleanly.
        """

        return (
            self.expected_value <= _MAX_PLAUSIBLE_COMBINED_EV
            and self.max_leg_edge <= _MAX_PLAUSIBLE_LEG_EDGE
        )


def _leg_from_report(report: SignalReport, lang: str, role: str) -> SlipLeg | None:
    signal = report.signal
    if not signal.is_bet or signal.chosen_outcome is None or signal.decimal_odds is None:
        return None
    metric = next(
        (m for m in signal.metrics if m.outcome is signal.chosen_outcome),
        None,
    )
    if metric is None:
        return None
    match = report.match
    return SlipLeg(
        match_id=match.match_id,
        match=f"{match.home_team.name} vs {match.away_team.name}",
        tip=plain_signal_label(signal.signal, lang, line=signal.totals_line),
        outcome=signal.chosen_outcome,
        odds=float(signal.decimal_odds),
        model_prob=float(metric.model_prob),
        edge=float(signal.edge or 0.0),
        role=role,
        league=match.league.value.replace("_", " ").title(),
        kickoff_date=match.kickoff.date().isoformat(),
        sport=(match.sport.value if getattr(match, "sport", None) is not None else ""),
    )


def _copy_leg(leg: SlipLeg, *, role: str) -> SlipLeg:
    return SlipLeg(
        match_id=leg.match_id,
        match=leg.match,
        tip=leg.tip,
        outcome=leg.outcome,
        odds=leg.odds,
        model_prob=leg.model_prob,
        edge=leg.edge,
        role=role,
        league=leg.league,
        kickoff_date=leg.kickoff_date,
        sport=leg.sport,
    )


def _value_legs(reports: list[SignalReport], lang: str) -> list[SlipLeg]:
    legs: list[SlipLeg] = []
    for report in reports:
        leg = _leg_from_report(report, lang, role="core")
        if leg is not None:
            legs.append(leg)
    return legs


def build_safe_slip(
    reports: list[SignalReport],
    *,
    lang: str = "de",
    max_legs: int = 3,
) -> BettingSlip | None:
    """Highest win-chance slip: value tips sorted by model probability."""

    legs = _value_legs(reports, lang)
    if not legs:
        return None
    legs.sort(key=lambda leg: (-leg.model_prob, -leg.edge))
    chosen = tuple(legs[: max(1, max_legs)])
    return BettingSlip(legs=chosen, style="safe")


def build_boosted_slip(
    reports: list[SignalReport],
    *,
    lang: str = "de",
    core_legs: int = 2,
    boost_legs: int = 2,
    min_boost_odds: float = 2.2,
) -> BettingSlip | None:
    """Safer core tips plus higher-odds legs to lift the combined price."""

    legs = _value_legs(reports, lang)
    if not legs:
        return None

    by_prob = sorted(legs, key=lambda leg: (-leg.model_prob, -leg.edge))
    core_n = max(1, min(core_legs, len(by_prob)))
    core = [_copy_leg(leg, role="core") for leg in by_prob[:core_n]]
    used = {leg.match_id for leg in core}

    boosters = [
        _copy_leg(leg, role="boost")
        for leg in sorted(by_prob, key=lambda leg: (-leg.odds, -leg.edge))
        if leg.match_id not in used and leg.odds >= min_boost_odds
    ][: max(0, boost_legs)]

    chosen = tuple(core + boosters)
    return BettingSlip(legs=chosen, style="boosted")


def slip_with_legs(slip: BettingSlip, match_ids: Sequence[str]) -> BettingSlip:
    """Keep only selected legs (order preserved); empty selection → empty slip."""

    wanted = set(match_ids)
    kept = tuple(leg for leg in slip.legs if leg.match_id in wanted)
    return BettingSlip(legs=kept, style=slip.style)


def default_leg_count(*, beginner: bool, span_days: int, available: int) -> int:
    """Sensible default tip count for a date window."""

    if available <= 0:
        return 1
    if beginner:
        # Short kombis: 2–3 tips, never more than available.
        return min(available, 3)
    suggested = min(8, max(3, span_days + 1))
    return min(available, suggested)




def build_smart_cross_sport_slip(
    reports: list[SignalReport],
    *,
    lang: str = "de",
    max_legs: int = 4,
    min_edge: float = 0.02,
    min_data_quality: float = 70.0,
    prefer_mixed: bool = True,
) -> BettingSlip | None:
    """Auto-pick top-value legs across sports under strict No-Bet gates.

    Requires edge > ``min_edge`` (default 2%) and data quality > ``min_data_quality``.
    When ``prefer_mixed`` is True and both sports have eligible legs, include at
    least one leg from each sport when ``max_legs`` >= 2.
    """

    eligible: list[tuple[SignalReport, SlipLeg]] = []
    for report in reports:
        signal = report.signal
        if not signal.is_bet:
            continue
        edge = float(signal.edge or 0.0)
        quality = float(signal.data_quality or 0.0)
        if edge <= min_edge or quality <= min_data_quality:
            continue
        leg = _leg_from_report(report, lang, role="core")
        if leg is not None:
            eligible.append((report, leg))

    if not eligible:
        return None

    def sort_key(item: tuple[SignalReport, SlipLeg]) -> tuple[float, float]:
        report, leg = item
        ev = float(report.signal.expected_value or 0.0)
        return (-ev, -leg.edge)

    eligible.sort(key=sort_key)
    max_legs = max(1, max_legs)

    chosen: list[SlipLeg] = []
    if prefer_mixed and max_legs >= 2:
        by_sport: dict[str, list[SlipLeg]] = {}
        for report, leg in eligible:
            sport = leg.sport or (
                report.match.sport.value
                if getattr(report.match, "sport", None) is not None
                else "football"
            )
            by_sport.setdefault(sport, []).append(leg)
        if len(by_sport) >= 2:
            for sport in sorted(by_sport.keys()):
                if len(chosen) >= max_legs:
                    break
                chosen.append(by_sport[sport][0])
            used = {leg.match_id for leg in chosen}
            for _, leg in eligible:
                if len(chosen) >= max_legs:
                    break
                if leg.match_id not in used:
                    chosen.append(leg)
                    used.add(leg.match_id)
            return BettingSlip(legs=tuple(chosen[:max_legs]), style="smart")

    chosen = [leg for _, leg in eligible[:max_legs]]
    return BettingSlip(legs=tuple(chosen), style="smart")


def format_ticket(
    slip: BettingSlip,
    *,
    lang: str = "de",
    stake: float = 10.0,
) -> str:
    """Plain-text tip-slip layout (copyable, beginner-friendly)."""

    de = lang.startswith("de")
    lines: list[str] = []
    lines.append("╔══════════════════════════════════════╗")
    title = "         TIPPSCHEIN (Vorschlag)         " if de else "       BETTING SLIP (suggestion)        "
    lines.append(f"║{title}║")
    kind = (
        "Kombi (hohe Modell-P)"
        if slip.style == "safe"
        else "Kombi mit Zusatz-Tipps"
    ) if de else (
        "Accumulator (high model-P)"
        if slip.style == "safe"
        else "Accumulator with extra tips"
    )
    lines.append(f"║  {kind:<36}║")
    lines.append("╠══════════════════════════════════════╣")
    for i, leg in enumerate(slip.legs, start=1):
        tip_short = leg.tip.replace("Tipp: ", "").replace("Tip: ", "")
        role = "  ★ Zusatz" if leg.role == "boost" and de else (
            "  ★ Extra" if leg.role == "boost" else ""
        )
        meta = " · ".join(p for p in (leg.kickoff_date, leg.league) if p)
        lines.append(f"║  {i}. {leg.match[:34]:<34}║")
        if meta:
            lines.append(f"║     {meta[:34]:<34}║")
        lines.append(f"║     → {tip_short[:20]:<20}  {leg.odds:>5.2f}{role:<8}║")
        if i < len(slip.legs):
            lines.append("║                                      ║")
    lines.append("╠══════════════════════════════════════╣")
    payout = stake * slip.combined_odds
    plausible = slip.is_plausible
    if de:
        lines.append(f"║  Einsatz:           {stake:>8.2f} €       ║")
        lines.append(f"║  Gesamtquote:       {slip.combined_odds:>8.2f}         ║")
        lines.append(f"║  Möglicher Gewinn:  {payout:>8.2f} €       ║")
        if plausible:
            lines.append(f"║  Geschätzte Chance: {slip.combined_prob * 100:>7.1f} %        ║")
        else:
            lines.append("║  Geschätzte Chance:   unrealistisch     ║")
    else:
        lines.append(f"║  Stake:             {stake:>8.2f}          ║")
        lines.append(f"║  Combined odds:     {slip.combined_odds:>8.2f}         ║")
        lines.append(f"║  Potential return:  {payout:>8.2f}          ║")
        if plausible:
            lines.append(f"║  Estimated chance:  {slip.combined_prob * 100:>7.1f} %        ║")
        else:
            lines.append("║  Estimated chance:    not realistic     ║")
    if not plausible:
        lines.append("╠══════════════════════════════════════╣")
        if de:
            lines.append("║  ⚠ Modellwerte zu hoch, meist zu     ║")
            lines.append("║    wenig Daten. Nicht verlässlich.   ║")
        else:
            lines.append("║  ⚠ Model values too high, usually    ║")
            lines.append("║    too little data. Not reliable.    ║")
    lines.append("╠══════════════════════════════════════╣")
    note = (
        "  Nur Vorschlag. QuantBot wettet nicht.  "
        if de
        else "  Suggestion only. QuantBot does not bet. "
    )
    lines.append(f"║{note}║")
    lines.append("╚══════════════════════════════════════╝")
    return "\n".join(lines)


def ticket_html(
    slip: BettingSlip,
    *,
    lang: str = "de",
    stake: float = 10.0,
) -> str:
    """HTML tip-slip that looks like a paper ticket."""

    de = lang.startswith("de")
    payout = stake * slip.combined_odds
    kind = (
        "Kombi (hohe Modell-P)"
        if slip.style == "safe"
        else "Kombi + Zusatz-Tipps"
    ) if de else (
        "Accumulator (high model-P)"
        if slip.style == "safe"
        else "Accumulator + extra tips"
    )
    rows: list[str] = []
    for i, leg in enumerate(slip.legs, start=1):
        tip_short = leg.tip.replace("Tipp: ", "").replace("Tip: ", "")
        match_name = escape(leg.match)
        tip_badge = tip_badge_html(tip_kind_from_label(leg.tip), lang, text=tip_short)
        badge = (
            (
                '<span style="color:#c47a00;font-size:0.8rem;margin-left:0.35rem;">★ Zusatz</span>'
                if de
                else '<span style="color:#c47a00;font-size:0.8rem;margin-left:0.35rem;">★ Extra</span>'
            )
            if leg.role == "boost"
            else ""
        )
        meta = " · ".join(p for p in (leg.kickoff_date, leg.league) if p)
        meta_line = (
            f'<div style="margin-top:2px;font-size:0.8rem;opacity:0.7;">{escape(meta)}</div>'
            if meta
            else ""
        )
        rows.append(
            "<tr>"
            f'<td style="padding:10px 8px;border-bottom:1px dashed #ccc;vertical-align:top;width:2rem;">{i}.</td>'
            f'<td style="padding:10px 8px;border-bottom:1px dashed #ccc;">'
            f'<div style="font-weight:700;">{match_name}</div>'
            f"{meta_line}"
            f'<div style="margin-top:4px;">→ {tip_badge} {badge}</div>'
            "</td>"
            f'<td style="padding:10px 8px;border-bottom:1px dashed #ccc;text-align:right;'
            f'font-size:1.15rem;font-weight:700;">{leg.odds:.2f}</td>'
            "</tr>"
        )
    stake_lbl = "Einsatz" if de else "Stake"
    odds_lbl = "Gesamtquote" if de else "Combined odds"
    win_lbl = "Möglicher Gewinn" if de else "Potential return"
    chance_lbl = "Geschätzte Chance" if de else "Estimated chance"
    title = "TIPPSCHEIN" if de else "BETTING SLIP"
    sub = (
        "Nur ein Vorschlag zum Abschreiben — QuantBot setzt nichts."
        if de
        else "Suggestion only — QuantBot places nothing."
    )
    currency = "€" if de else ""
    if slip.is_plausible:
        chance_row = (
            f'<div style="display:flex;justify-content:space-between;margin:0.25rem 0;"><span>{chance_lbl}</span>'
            f"<b>{slip.combined_prob * 100:.1f} %</b></div>"
        )
    else:
        warn = (
            "Modellwerte unrealistisch — meist zu wenig Daten. Nicht verlässlich."
            if de
            else "Model values unrealistic — usually too little data. Not reliable."
        )
        chance_row = (
            f'<div style="display:flex;justify-content:space-between;margin:0.25rem 0;"><span>{chance_lbl}</span>'
            f'<b style="color:#b00020;">{"unrealistisch" if de else "not realistic"}</b></div>'
            f'<div style="margin-top:0.4rem;padding:0.4rem 0.5rem;background:#fce8e6;color:#b00020;'
            f'border-radius:4px;font-size:0.8rem;">⚠ {warn}</div>'
        )
    return (
        '<div style="max-width:520px;margin:0.5rem 0 1rem 0;padding:1.25rem 1.4rem;'
        "background:linear-gradient(180deg,#fffef8 0%,#f7f1e1 100%);"
        "color:#1a1a1a;border:2px solid #222;border-radius:6px;"
        'box-shadow:4px 4px 0 #222;font-family:ui-monospace,Menlo,Consolas,monospace;">'
        f'<div style="text-align:center;letter-spacing:0.18em;font-weight:800;font-size:1.25rem;">{title}</div>'
        f'<div style="text-align:center;margin:0.35rem 0 0.9rem 0;font-size:0.9rem;">{kind}</div>'
        f'<table style="width:100%;border-collapse:collapse;">{"".join(rows)}</table>'
        '<div style="margin-top:1rem;padding-top:0.75rem;border-top:2px solid #222;">'
        f'<div style="display:flex;justify-content:space-between;margin:0.25rem 0;"><span>{stake_lbl}</span>'
        f"<b>{stake:.2f} {currency}</b></div>"
        f'<div style="display:flex;justify-content:space-between;margin:0.25rem 0;"><span>{odds_lbl}</span>'
        f"<b>{slip.combined_odds:.2f}</b></div>"
        f'<div style="display:flex;justify-content:space-between;margin:0.25rem 0;font-size:1.15rem;">'
        f"<span>{win_lbl}</span><b>{payout:.2f} {currency}</b></div>"
        f"{chance_row}"
        "</div>"
        f'<div style="margin-top:0.9rem;text-align:center;font-size:0.8rem;opacity:0.8;">{sub}</div>'
        "</div>"
    )
