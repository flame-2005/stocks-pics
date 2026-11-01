"""Telegram message formatting (HTML). Everything dynamic goes through esc()."""
from __future__ import annotations

from datetime import date
from html import escape

from . import config
from .plan import TradePlan, discipline_rules
from .scoring import Candidate, FunnelCounts
from .sectors import SectorStrength
from .sentiment import MarketMood
from .universe import sector_short
from .util import fmt_inr

MOOD_ICON = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡", "no_trade": "⛔"}
SIDE_WORD = {"long": "BUY", "short": "SELL"}


def esc(value) -> str:
    return escape(str(value), quote=False)


def _date(d: date | str) -> str:
    d = date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%a %d %b %Y")


def mood_block(mood: MarketMood, detailed: bool = True) -> str:
    icon = MOOD_ICON.get(mood.label, "")
    lines = [f"{icon} <b>Market mood: {esc(mood.label.replace('_', ' ').upper())}</b> (score {mood.score:+d})"]
    if detailed:
        for c in mood.components:
            if c.note:
                sign = f" [{c.points:+d}]" if c.points else ""
                lines.append(f"  • {esc(c.note)}{sign}")
    for r in mood.reasons:
        lines.append(f"  ⚠ {esc(r)}")
    return "\n".join(lines)


def funnel_line(counts: FunnelCounts) -> str:
    return (
        f"Funnel: {counts.universe} → {counts.filters_passed} pass filters → {counts.funnel} liquid → "
        f"{counts.with_setup} with setup → {counts.sector_ok} in ok sectors → <b>{counts.final} picks</b>"
    )


def sector_block(sectors: list[SectorStrength], n: int = 3) -> str:
    if not sectors:
        return ""
    top = ", ".join(f"{esc(sector_short(s.sector))} {s.rs_5d:+.1f}%" for s in sectors[:n])
    bottom = ", ".join(f"{esc(sector_short(s.sector))} {s.rs_5d:+.1f}%" for s in sectors[-n:])
    return f"Sectors vs Nifty (5d): strong {top} · weak {bottom}"


def pick_block(p: TradePlan, idx: int) -> str:
    side = SIDE_WORD[p.side]
    trigger = "above" if p.side == "long" else "below"
    stop_dir = "-" if p.side == "long" else "+"
    lines = [
        f"<b>{idx}. {esc(p.symbol)}</b> · {side} · {esc(sector_short(p.industry))} · score {p.score:g}",
        f"   {side} {trigger} ₹{fmt_inr(p.entry)} · SL ₹{fmt_inr(p.stop)} ({stop_dir}{p.stop_pct:g}%) · "
        f"Target ₹{fmt_inr(p.target)} ({abs(p.target - p.entry) / max(abs(p.entry - p.stop), 1e-9):.1f}R)",
        f"   Qty {p.qty} · risk ₹{fmt_inr(p.risk_amount, 0)} · notional ₹{fmt_inr(p.notional, 0)}",
    ]
    if p.reasons:
        lines.append(f"   Why: {esc('; '.join(p.reasons[:3]))}")
    for flag in p.flags:
        lines.append(f"   ⚠ {esc(flag)}")
    if p.note:
        lines.append(f"   ℹ {esc(p.note)}")
    return "\n".join(lines)


def shortlist_block(cands: list[Candidate], n: int = 12) -> str:
    seen: set[tuple[str, str]] = set()
    items = []
    for c in cands:
        key = (c.symbol, c.side)
        if key in seen:
            continue
        seen.add(key)
        side = "L" if c.side == "long" else "S"
        items.append(f"{esc(c.symbol)} ({side}, {esc(c.setup_type or '-')}, {c.score:g})")
        if len(items) >= n:
            break
    return "Shortlist: " + ", ".join(items) if items else "Shortlist: none with a setup"


def rules_block() -> str:
    return "<b>Rules</b>\n" + "\n".join(f"  • {esc(r)}" for r in discipline_rules())


def links_block() -> str:
    links = " · ".join(f'<a href="{url}">{esc(name)}</a>' for name, url in config.MANUAL_CHECK_LINKS.items())
    return f"Manual check: {links}"


def prep_message(trade_date, mood: MarketMood, counts: FunnelCounts, shortlist: list[Candidate],
                 plans: list[TradePlan], sectors: list[SectorStrength], candidates: list[Candidate] | None = None) -> str:
    parts = [f"📋 <b>Watchlist for {_date(trade_date)}</b> (prepared the evening before)", mood_block(mood, detailed=False)]
    parts.append(funnel_line(counts).replace("picks", "candidates") if candidates is not None else funnel_line(counts))
    sb = sector_block(sectors)
    if sb:
        parts.append(sb)
    parts.append(shortlist_block(shortlist))
    if candidates is not None:
        longs = ", ".join(esc(c.symbol) for c in candidates if c.side == "long") or "none"
        shorts = ", ".join(esc(c.symbol) for c in candidates if c.side == "short") or "none"
        parts.append(
            "The side is decided at 09:34 from the Nifty's opening candle.\n"
            f"BUY candidates if it opens up: {longs}\nSELL candidates if it opens down: {shorts}\n"
            "Final candidates come at 09:10 after global cues and pre-open."
        )
    elif plans:
        parts.append("<b>Provisional picks</b> (final list comes at 09:10 after global cues and pre-open):")
        parts.extend(pick_block(p, i) for i, p in enumerate(plans, start=1))
    else:
        parts.append("No pick clears the bar yet; the 09:10 run re-checks with pre-open data.")
    return "\n\n".join(parts)


def morning_message(trade_date, mood: MarketMood, counts: FunnelCounts, plans: list[TradePlan],
                    guards: dict | None = None) -> str:
    parts = [f"🔔 <b>Intraday picks for {_date(trade_date)}</b>", mood_block(mood)]
    parts.append(funnel_line(counts))
    if guards:
        notes = []
        if guards.get("results"):
            notes.append("results today: " + ", ".join(esc(s) for s in guards["results"]))
        if guards.get("ban"):
            notes.append("F&O ban: " + ", ".join(esc(s) for s in guards["ban"]))
        if guards.get("gap_skipped"):
            notes.append("gap > 3%: " + ", ".join(esc(s) for s in guards["gap_skipped"]))
        if notes:
            parts.append("Excluded → " + " · ".join(notes))
    if plans:
        parts.extend(pick_block(p, i) for i, p in enumerate(plans, start=1))
        parts.append(f"Entry windows {esc(plans[0].entry_window)} · square off by {esc(plans[0].squareoff)}")
    else:
        parts.append("No pick clears the bar today. Sitting out is a position.")
    parts.append(rules_block())
    parts.append(links_block())
    return "\n\n".join(parts)


def no_trade_message(trade_date, mood: MarketMood, counts: FunnelCounts | None = None) -> str:
    parts = [f"⛔ <b>No trades today: {_date(trade_date)}</b>", mood_block(mood)]
    if counts:
        parts.append(funnel_line(counts))
    parts.append("The playbook says sit out when the market mood is this unclear or volatile. Capital preserved is capital earned.")
    return "\n\n".join(parts)


def confirm_message(trade_date, results: list) -> str:
    icon = {"confirmed": "✅", "cancelled": "❌", "pending": "⏳"}
    parts = [f"🕤 <b>09:30 candle check for {_date(trade_date)}</b>"]
    for r in results:
        head = f"{icon.get(r.status, '•')} <b>{esc(r.symbol)}</b> {SIDE_WORD[r.side]}: {esc(r.status)}"
        body = []
        if r.first_close is not None:
            body.append(f"first candle O {fmt_inr(r.first_open)} H {fmt_inr(r.first_high)} L {fmt_inr(r.first_low)} C {fmt_inr(r.first_close)}")
        if r.note:
            body.append(esc(r.note))
        if r.status == "confirmed" and r.suggested_entry:
            body.append(f"enter {'above' if r.side == 'long' else 'below'} ₹{fmt_inr(r.suggested_entry)}, SL ₹{fmt_inr(r.suggested_stop)}")
        parts.append(head + ("\n   " + "\n   ".join(body) if body else ""))
    confirmed = sum(1 for r in results if r.status == "confirmed")
    parts.append(f"{confirmed} confirmed. Max {config.MAX_TRADES_PER_DAY} trades; stop at the daily loss cap.")
    return "\n\n".join(parts)


def scorecard_message(trade_date, outcomes: list[dict], nifty_ret: float | None, stats: dict) -> str:
    icon = {"target": "🎯", "stop": "🛑", "eod_close": "🔚", "no_entry": "➖", "skipped": "·"}
    nifty = f"Nifty {nifty_ret:+.2f}%" if nifty_ret is not None else "Nifty n/a"
    parts = [f"📊 <b>Scorecard {_date(trade_date)}</b> · {nifty}"]
    for o in outcomes:
        r = o.get("r_multiple")
        r_txt = f"{r:+.2f}R" if r is not None else ""
        pnl = o.get("pnl")
        pnl_txt = f" ₹{fmt_inr(pnl, 0)}" if pnl is not None else ""
        status = o.get("status", "")
        line = f"{icon.get(o.get('result'), '•')} {esc(o['symbol'])} {SIDE_WORD.get(o['side'], '')} ({esc(status)}): {esc(o.get('result'))} {r_txt}{pnl_txt}"
        parts.append(line)
    if stats:
        parts.append(
            f"Confirmed picks: {stats.get('n', 0)} · hits {stats.get('targets', 0)} · stops {stats.get('stops', 0)} · "
            f"total {stats.get('total_r', 0.0):+.2f}R · running {stats.get('cum_r', 0.0):+.1f}R over {stats.get('days', 0)} days"
        )
    return "\n\n".join(parts)


# ----------------------------------------------------------------------------- opening-range mode
def orb_candidates_message(trade_date, mood: MarketMood, counts: FunnelCounts, longs: list[Candidate],
                           shorts: list[Candidate], guards: dict | None = None) -> str:
    parts = [f"🔔 <b>Candidates for {_date(trade_date)}</b>", mood_block(mood)]
    parts.append(funnel_line(counts).replace("picks", "candidates"))
    parts.append(
        "The side is decided at <b>09:34</b> from the Nifty's opening 15-minute candle "
        f"(needs a move of at least {esc(f'{0.10:.2f}')}%); each stock must confirm on its own candle."
    )
    for label, cands in (("If the Nifty opens up → BUY candidates", longs), ("If the Nifty opens down → SELL candidates", shorts)):
        if cands:
            items = ", ".join(f"<b>{esc(c.symbol)}</b> ({esc(c.setup_label or c.setup_type or '-')}, {c.score:g})" for c in cands)
        else:
            items = "none with a setup"
        parts.append(f"{label}:\n{items}")
    if guards:
        notes = []
        for key, text in (("results", "results today"), ("ban", "F&O ban"), ("gap_skipped", "gap > 3%")):
            if guards.get(key):
                notes.append(f"{text}: " + ", ".join(esc(s) for s in guards[key]))
        if notes:
            parts.append("Excluded → " + " · ".join(notes))
    parts.append(rules_block())
    return "\n\n".join(parts)


def orb_decision_message(trade_date, direction: str, nifty_pct: float | None, plans: list[TradePlan],
                         rejected: list[tuple[str, list[str]]], caution: bool = False) -> str:
    arrow = {"up": "🟢 Nifty opened UP", "down": "🔴 Nifty opened DOWN", "flat": "🟡 Nifty opening candle flat"}[direction]
    pct = f" ({nifty_pct:+.2f}%)" if nifty_pct is not None else ""
    parts = [f"🕤 <b>09:34 decision for {_date(trade_date)}</b>", f"{arrow}{pct}"]
    if direction == "flat":
        parts.append("No direction, no trade. Sitting out is a position.")
    elif plans:
        side_word = "BUY" if plans[0].side == "long" else "SELL"
        parts.append(f"<b>{side_word} side today.</b> Enter on a break of the opening-candle {'high' if plans[0].side == 'long' else 'low'}, "
                     f"stop at the other end, first target {config.ORB_TARGET_R:g}R, no new entries after "
                     f"{config.ORB_ENTRY_DEADLINE.strftime('%H:%M')}, square off by {config.SQUAREOFF.strftime('%H:%M')}.")
        if caution:
            parts.append("⚠ Caution flag from the morning run: half size.")
        parts.extend(pick_block(p, i) for i, p in enumerate(plans, start=1))
    else:
        parts.append("Nifty gave a direction but no candidate confirmed on its own opening candle. No trade.")
    if rejected:
        parts.append("Not confirmed: " + " · ".join(f"{esc(sym)} ({esc('; '.join(why))})" for sym, why in rejected[:8]))
    parts.append(f"Max {config.MAX_TRADES_PER_DAY} trades; stop for the day at the loss cap.")
    return "\n\n".join(parts)


# ----------------------------------------------------------------------------- your list (focus)
VERDICT_WORD = {"lean_buy": "lean BUY", "lean_sell": "lean SELL", "buy": "BUY", "sell": "SELL", "no": "NO"}
VERDICT_ICON = {"lean_buy": "🟢", "lean_sell": "🔴", "buy": "🟢", "sell": "🔴", "no": "⚪"}


def _get(v, key):
    return v.get(key) if isinstance(v, dict) else getattr(v, key, None)


def focus_block(verdicts, phase: str) -> str:
    """One line per symbol in the user's list. `phase`: prep | morning | orb | scorecard."""
    if not verdicts:
        return ""
    title = {
        "prep": "Your list (lean for tomorrow; decided at 09:34)",
        "morning": "Your list (lean; decided at 09:34)",
        "orb": "Your list: 09:34 verdicts",
        "scorecard": "Your list: results",
    }[phase]
    lines = [f"<b>{esc(title)}</b>"]
    for v in verdicts:
        verdict = _get(v, "verdict") or "no"
        word = VERDICT_WORD.get(verdict, "NO")
        strength = f" ({esc(_get(v, 'strength'))})" if _get(v, "strength") else ""
        name = esc(_get(v, "symbol"))
        if _get(v, "symbol") == "NIFTY" and verdict in ("buy", "sell"):
            name += f" via {esc(config.FOCUS_NIFTY_INSTRUMENT)}"
        parts = [f"{VERDICT_ICON.get(verdict, '⚪')} <b>{name}</b>: {word}{strength}"]
        if verdict in ("buy", "sell") and _get(v, "entry"):
            trigger = "above" if _get(v, "side") == "long" else "below"
            parts.append(
                f"   {word} {trigger} ₹{fmt_inr(_get(v, 'entry'))} · SL ₹{fmt_inr(_get(v, 'stop'))} "
                f"({_get(v, 'stop_pct'):g}%) · target ₹{fmt_inr(_get(v, 'target'))} · qty {_get(v, 'qty')}"
            )
        reasons = _get(v, "reasons") or []
        if reasons:
            parts.append("   " + esc("; ".join(reasons[:3])))
        for fl in (_get(v, "flags") or [])[:3]:
            parts.append(f"   ⚠ {esc(fl)}")
        if _get(v, "note"):
            parts.append(f"   ℹ {esc(_get(v, 'note'))}")
        if phase == "scorecard" and _get(v, "result"):
            r = _get(v, "r_multiple")
            pnl = _get(v, "pnl")
            tail = f" {r:+.2f}R" if r is not None else ""
            tail += f" ₹{fmt_inr(pnl, 0)}" if pnl is not None else ""
            parts.append(f"   → {esc(_get(v, 'result'))}{tail}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)
