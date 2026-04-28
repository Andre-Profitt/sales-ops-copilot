#!/usr/bin/env python3
"""Sales Ops Cockpit — Textual TUI consolidating alerts, deals, ack state, and concentration.

3-pane layout: alerts (left) -> deal samples (center) -> deal drill (right).
Reads live data via brief.pull_salesforce_snapshot() + alerts.pull_all_alerts() etc.
Ack writes hit ack.add() so the existing persistence layer stays canonical.

Run:
    python3 scripts/cockpit.py              # full live pull
    python3 scripts/cockpit.py --no-fetch   # cached snapshot only (offline/dev)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

# sys.path so sibling scripts (alerts, ack, brief) import as modules
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, Container
from textual.reactive import reactive
from textual.widgets import DataTable, Input, Static, Label

import ack  # type: ignore[import-not-found]

STATE_DIR = SCRIPT_DIR.parent / "state"
SNAP_DIR = STATE_DIR / "snapshots"

SEV_GLYPH = {
    "critical": "[b red]●[/]",
    "important": "[yellow]▲[/]",
    "info": "[blue]◇[/]",
    "error": "[red]![/]",
}
SEV_ORDER = {"critical": 0, "important": 1, "info": 2, "error": 99}


def _fmt_money(n: float | int | None) -> str:
    if not n:
        return "$0"
    n = float(n)
    if n >= 1_000_000:
        return f"${n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"${n / 1_000:.0f}K"
    return f"${n:.0f}"


def _today_snapshot() -> dict[str, Any] | None:
    """Most recent daily snapshot file, if any."""
    if not SNAP_DIR.exists():
        return None
    files = sorted(SNAP_DIR.glob("[0-9]*-[0-9]*-[0-9]*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text())
    except json.JSONDecodeError:
        return None


def _today_alert_counts() -> dict[str, Any] | None:
    if not SNAP_DIR.exists():
        return None
    files = sorted(SNAP_DIR.glob("*_alerts.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text())
    except json.JSONDecodeError:
        return None


def _alerts_from_cache() -> list[dict[str, Any]]:
    """Reconstruct alert shape from cached *_alerts.json (no samples — counts/totals only)."""
    cache = _today_alert_counts()
    if not cache:
        return []
    counts: dict[str, int] = cache.get("counts", {})
    totals: dict[str, float] = cache.get("total_arr", {})

    # Best-effort severity guess from name
    def _sev(n: str) -> str:
        n = n.lower()
        if "without commercial approval" in n or "kyc" in n or "close date in the past" in n:
            return "critical"
        if "submitted but not yet" in n:
            return "info"
        return "important"

    out: list[dict[str, Any]] = []
    for name, count in counts.items():
        if count <= 0:
            continue
        out.append(
            {
                "name": name,
                "severity": _sev(name),
                "count": count,
                "total_arr": totals.get(name, 0) or 0,
                "samples": [],
                "rule": "(cached — run without --no-fetch for samples)",
            }
        )
    out.sort(key=lambda a: (SEV_ORDER.get(a["severity"], 99), -a["total_arr"]))
    return out


# ---------------------------------------------------------------------------


class HelpOverlay(Container):
    DEFAULT_CSS = ""

    def compose(self) -> ComposeResult:
        with Container(id="help-box"):
            yield Static(
                "[b]Sales Ops Cockpit — keybindings[/b]\n\n"
                "  [b]j/k[/]  or  [b]↑/↓[/]   move within focused pane\n"
                "  [b]tab[/]                 cycle focus between panes\n"
                "  [b]enter[/]               drill: alert → deals → drill\n"
                "  [b]a[/]                   ack the selected deal (7d)\n"
                "  [b]r[/]                   refresh (live SF pull)\n"
                "  [b]/[/]                   filter focused pane (esc clears)\n"
                "  [b]o[/]                   toggle owner concentration overlay\n"
                "  [b]?[/]                   toggle this help\n"
                "  [b]q[/]  /  [b]ctrl+c[/]  quit\n\n"
                "[dim]ARR = Land+Expand · ACV = Renewal · never blended[/dim]"
            )


class OwnerOverlay(Container):
    """Top owner-concentration overlay (toggle with `o`)."""

    def compose(self) -> ComposeResult:
        with Container(id="help-box"):
            yield Label("[b]Owner concentration — top 10 by flagged ARR[/b]", id="owner-title")
            yield DataTable(id="owner-table", cursor_type="row", zebra_stripes=True)


# ---------------------------------------------------------------------------


class Cockpit(App):
    CSS_PATH = "cockpit.tcss"

    BINDINGS = [
        Binding("q", "quit", "quit", show=True),
        Binding("ctrl+c", "quit", "quit", show=False),
        Binding("?", "toggle_help", "help", show=True),
        Binding("r", "refresh", "refresh", show=True),
        Binding("a", "ack", "ack", show=True),
        Binding("o", "toggle_owner", "owner", show=True),
        Binding("/", "start_search", "search", show=True),
        Binding("tab", "cycle_focus", "focus", show=False, priority=True),
        Binding("enter", "drill", "drill", show=False),
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("escape", "escape", show=False),
    ]

    headline: reactive[str] = reactive("loading…")
    show_help: reactive[bool] = reactive(False)
    show_owner: reactive[bool] = reactive(False)
    fetch_live: bool = True

    def __init__(self, fetch_live: bool = True) -> None:
        super().__init__()
        self.fetch_live = fetch_live
        self.alerts: list[dict[str, Any]] = []
        self.snapshot: dict[str, Any] = {}
        self.owners: list[dict[str, Any]] = []
        self.accounts: list[dict[str, Any]] = []
        self.last_pull_secs: float = 0.0
        self._search_target: str | None = None
        self._all_samples_for_alert: list[dict[str, Any]] = []
        self._filtered_samples: list[dict[str, Any]] = []
        self._acked_local: set[str] = set()  # session-marked acked deals

    def compose(self) -> ComposeResult:
        yield Static("", id="topbar")
        with Horizontal(id="panes"):
            with Vertical(id="alerts-pane"):
                yield Label("[b]Alerts[/b]", id="alerts-title")
                yield DataTable(id="alerts-table", cursor_type="row", zebra_stripes=True)
            with Vertical(id="deals-pane"):
                yield Label("[b]Deals[/b]", id="deals-title")
                yield DataTable(id="deals-table", cursor_type="row", zebra_stripes=True)
            with Vertical(id="drill-pane"):
                yield Label("[b]Drill[/b]", id="drill-title")
                yield Static("(select a deal in the center pane)", id="drill-body")
        yield Static("", id="toast")
        with Container(id="search-bar"):
            yield Input(placeholder="filter…", id="search-input")
        yield Static(
            "[dim]j/k move · tab focus · enter drill · a ack · r refresh · / search · ? help · q quit[/dim]",
            id="bottombar",
        )

    # ------------------------------------------------------------------ mount
    def on_mount(self) -> None:
        self._setup_alerts_table()
        self._setup_deals_table()
        self.headline = "loading…"
        self._set_topbar()
        self.query_one("#alerts-pane").add_class("focused")
        if self.fetch_live:
            self._toast("Loading live pipeline + alerts… (~5s)", kind="info")
            self.load_live()
        else:
            self.load_cache()

    def _setup_alerts_table(self) -> None:
        t = self.query_one("#alerts-table", DataTable)
        t.add_columns("sev", "alert", "count", "$ARR")
        t.zebra_stripes = True

    def _setup_deals_table(self) -> None:
        t = self.query_one("#deals-table", DataTable)
        t.add_columns("name", "stage", "$ARR", "owner")
        t.zebra_stripes = True

    # ------------------------------------------------------------------ data
    @work(thread=True, exclusive=True)
    def load_live(self) -> None:
        t0 = time.monotonic()
        try:
            from alerts import (  # type: ignore[import-not-found]
                pull_all_alerts,
                pull_owner_concentration,
                pull_account_concentration,
            )
            from brief import pull_salesforce_snapshot  # type: ignore[import-not-found]

            alerts_data = pull_all_alerts()
            snap = pull_salesforce_snapshot()
            owners = pull_owner_concentration(top_n=10)
            accounts = pull_account_concentration(top_n=15)
            self.last_pull_secs = time.monotonic() - t0
            self.call_from_thread(self._apply_data, alerts_data, snap, owners, accounts, None)
        except Exception as exc:  # pragma: no cover — surfaced in UI
            self.call_from_thread(self._apply_data, [], {}, [], [], str(exc))

    def load_cache(self) -> None:
        t0 = time.monotonic()
        snap = _today_snapshot() or {}
        alerts_data = _alerts_from_cache()
        self.last_pull_secs = time.monotonic() - t0
        self._apply_data(alerts_data, snap, [], [], None)
        if not alerts_data:
            self._toast("no cached snapshot found — try without --no-fetch", kind="error")

    def _apply_data(
        self,
        alerts_data: list[dict[str, Any]],
        snap: dict[str, Any],
        owners: list[dict[str, Any]],
        accounts: list[dict[str, Any]],
        err: str | None,
    ) -> None:
        if err:
            self._toast(f"load failed: {err[:80]}", kind="error")
            return
        # cache last good
        if alerts_data:
            self.alerts = alerts_data
        if snap:
            self.snapshot = snap
        if owners:
            self.owners = owners
        if accounts:
            self.accounts = accounts
        self._render_topbar()
        self._render_alerts_table()
        # Pre-select first alert and populate deals
        t = self.query_one("#alerts-table", DataTable)
        if t.row_count:
            t.move_cursor(row=0)
            self._on_alert_selected(0)

    # ------------------------------------------------------------------ render
    def _render_topbar(self) -> None:
        totals = (self.snapshot or {}).get("totals", {}) or {}
        # Backward compat: top-level totals or quarter[0]
        nb_open = totals.get("new_business_arr_open_this_quarter", 0)
        nb_w = totals.get("weighted_new_business_arr", 0)
        if not nb_w and self.snapshot.get("quarters"):
            nb_w = self.snapshot["quarters"][0].get("weighted_new_business_arr", 0)
        n_alerts = len(self.alerts)
        n_acks = len(ack.active_ids())
        pull = f" · pulled in {self.last_pull_secs:.1f}s" if self.last_pull_secs else ""
        self.headline = (
            f"Q open ARR {_fmt_money(nb_open)} / weighted {_fmt_money(nb_w)}"
            f" · {n_alerts} alerts · {n_acks} acks active{pull}"
        )
        self._set_topbar()

    def _set_topbar(self) -> None:
        bar = self.query_one("#topbar", Static)
        mode = "[dim](cached)[/]" if not self.fetch_live else ""
        bar.update(f"[b]Sales Ops Cockpit[/b] {mode}    {self.headline}")

    def _render_alerts_table(self) -> None:
        t = self.query_one("#alerts-table", DataTable)
        t.clear()
        for a in self.alerts:
            sev = a.get("severity", "info")
            glyph = SEV_GLYPH.get(sev, "·")
            name = a.get("name", "?")
            if len(name) > 38:
                name = name[:35] + "…"
            t.add_row(glyph, name, str(a.get("count", 0)), _fmt_money(a.get("total_arr", 0)))

    def _render_deals_for_alert(self, idx: int) -> None:
        t = self.query_one("#deals-table", DataTable)
        t.clear()
        title = self.query_one("#deals-title", Label)
        if idx < 0 or idx >= len(self.alerts):
            title.update("[b]Deals[/b]")
            self._all_samples_for_alert = []
            self._filtered_samples = []
            return
        alert = self.alerts[idx]
        samples = list(alert.get("samples") or [])
        self._all_samples_for_alert = samples
        self._filtered_samples = samples
        title.update(
            f"[b]Deals[/b]  [dim]({len(samples)} samples in {alert.get('name', '?')[:40]})[/dim]"
        )
        for s in samples:
            self._add_deal_row(t, s)
        if t.row_count:
            t.move_cursor(row=0)
            self._render_drill_for_deal(0)

    def _add_deal_row(self, t: DataTable, s: dict[str, Any]) -> None:
        name = s.get("name") or s.get("Name") or "?"
        if len(name) > 32:
            name = name[:29] + "…"
        stage = s.get("stage") or s.get("StageName") or ""
        arr = s.get("$arr") or s.get("APTS_Opportunity_ARR__c") or 0
        owner = s.get("owner") or "—"
        if len(owner) > 18:
            owner = owner[:15] + "…"
        opp_id = s.get("id") or ""
        if opp_id in self._acked_local:
            name = f"[strike dim]{name}[/]"
            stage = f"[dim]{stage}[/]"
            owner = f"[dim]{owner}[/]"
        t.add_row(name, stage, _fmt_money(arr), owner, key=opp_id or None)

    def _render_drill_for_deal(self, row_idx: int) -> None:
        body = self.query_one("#drill-body", Static)
        if row_idx < 0 or row_idx >= len(self._filtered_samples):
            body.update("(select a deal in the center pane)")
            return
        s = self._filtered_samples[row_idx]
        opp_id = s.get("id", "")
        name = s.get("name", "?")
        stage = s.get("stage", "?")
        arr = s.get("$arr", 0)
        owner = s.get("owner", "—")
        also = s.get("also_flagged_in") or []
        lines = [
            f"[b]{name}[/b]",
            f"[dim]{opp_id}[/dim]",
            "",
            f"  stage:    {stage}",
            f"  ARR:      {_fmt_money(arr)}",
            f"  owner:    {owner}",
        ]
        for k in (
            "closedate",
            "lastactivitydate",
            "createddate",
            "submit_for_stage_20_review_date__c",
        ):
            if k in s:
                lines.append(f"  {k:<9} {s[k]}")
        if also:
            lines.append("")
            lines.append("[b]also flagged in:[/b]")
            for n in also:
                lines.append(f"  · {n}")
        if opp_id in self._acked_local:
            lines.append("")
            lines.append("[yellow]ACKED this session — will drop from next refresh[/yellow]")
        body.update("\n".join(lines))

    # ------------------------------------------------------------------ events
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        tid = event.data_table.id
        idx = event.cursor_row
        if tid == "alerts-table":
            self._on_alert_selected(idx)
        elif tid == "deals-table":
            self._render_drill_for_deal(idx)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        tid = event.data_table.id
        if tid == "alerts-table":
            self._focus_pane("deals-pane")
        elif tid == "deals-table":
            self._focus_pane("drill-pane")

    def _on_alert_selected(self, idx: int) -> None:
        self._render_deals_for_alert(idx)

    # ------------------------------------------------------------------ actions
    def action_cursor_down(self) -> None:
        t = self._focused_table()
        if t is not None and t.row_count:
            t.action_cursor_down()

    def action_cursor_up(self) -> None:
        t = self._focused_table()
        if t is not None and t.row_count:
            t.action_cursor_up()

    def action_cycle_focus(self) -> None:
        order = ["alerts-pane", "deals-pane", "drill-pane"]
        current = self._focused_pane_id()
        nxt = order[(order.index(current) + 1) % len(order)] if current in order else order[0]
        self._focus_pane(nxt)

    def action_drill(self) -> None:
        cur = self._focused_pane_id()
        if cur == "alerts-pane":
            self._focus_pane("deals-pane")
        elif cur == "deals-pane":
            self._focus_pane("drill-pane")

    def action_ack(self) -> None:
        if self._focused_pane_id() != "deals-pane":
            self._toast("focus the deals pane to ack a deal", kind="error")
            return
        t = self.query_one("#deals-table", DataTable)
        if not t.row_count:
            return
        idx = t.cursor_row
        if idx < 0 or idx >= len(self._filtered_samples):
            return
        s = self._filtered_samples[idx]
        opp_id = s.get("id")
        if not opp_id:
            self._toast("no opp ID on this row", kind="error")
            return
        ack.add(opp_id, days=7, note=None)
        self._acked_local.add(opp_id)
        # Re-render the row in place (without rebuilding entire table)
        self._refresh_deals_table_keep_cursor()
        self._toast(f"acked {opp_id} for 7d", kind="info")

    def action_refresh(self) -> None:
        if not self.fetch_live:
            self.fetch_live = True  # promote into live mode on demand
        self._toast("refreshing…", kind="info")
        self.load_live()

    def action_toggle_help(self) -> None:
        self.show_help = not self.show_help
        self._render_overlay()

    def action_toggle_owner(self) -> None:
        self.show_owner = not self.show_owner
        self._render_overlay()

    def action_start_search(self) -> None:
        self._search_target = self._focused_pane_id()
        bar = self.query_one("#search-bar")
        bar.add_class("visible")
        inp = self.query_one("#search-input", Input)
        inp.value = ""
        inp.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "search-input":
            return
        self._apply_filter(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search-input":
            return
        self._end_search()

    def action_escape(self) -> None:
        if self.show_help or self.show_owner:
            self.show_help = False
            self.show_owner = False
            self._render_overlay()
            return
        if self.query_one("#search-bar").has_class("visible"):
            self._end_search(clear=True)

    # ------------------------------------------------------------------ helpers
    def _focused_pane_id(self) -> str:
        for pid in ("alerts-pane", "deals-pane", "drill-pane"):
            if self.query_one(f"#{pid}").has_class("focused"):
                return pid
        return "alerts-pane"

    def _focus_pane(self, pane_id: str) -> None:
        for pid in ("alerts-pane", "deals-pane", "drill-pane"):
            self.query_one(f"#{pid}").remove_class("focused")
        self.query_one(f"#{pane_id}").add_class("focused")
        if pane_id == "alerts-pane":
            self.query_one("#alerts-table", DataTable).focus()
        elif pane_id == "deals-pane":
            self.query_one("#deals-table", DataTable).focus()

    def _focused_table(self) -> DataTable | None:
        pid = self._focused_pane_id()
        if pid == "alerts-pane":
            return self.query_one("#alerts-table", DataTable)
        if pid == "deals-pane":
            return self.query_one("#deals-table", DataTable)
        return None

    def _refresh_deals_table_keep_cursor(self) -> None:
        t = self.query_one("#deals-table", DataTable)
        cur = t.cursor_row
        t.clear()
        for s in self._filtered_samples:
            self._add_deal_row(t, s)
        if t.row_count and cur < t.row_count:
            t.move_cursor(row=cur)
        self._render_drill_for_deal(cur)

    def _apply_filter(self, q: str) -> None:
        target = self._search_target
        q = (q or "").strip().lower()
        if target == "alerts-pane":
            t = self.query_one("#alerts-table", DataTable)
            t.clear()
            for a in self.alerts:
                if q and q not in (a.get("name", "")).lower():
                    continue
                sev = a.get("severity", "info")
                glyph = SEV_GLYPH.get(sev, "·")
                name = a.get("name", "?")
                if len(name) > 38:
                    name = name[:35] + "…"
                t.add_row(glyph, name, str(a.get("count", 0)), _fmt_money(a.get("total_arr", 0)))
        elif target == "deals-pane":
            self._filtered_samples = [
                s
                for s in self._all_samples_for_alert
                if not q
                or q in (s.get("name", "")).lower()
                or q in (s.get("owner", "")).lower()
                or q in (s.get("stage", "")).lower()
            ]
            self._refresh_deals_table_keep_cursor()

    def _end_search(self, clear: bool = False) -> None:
        bar = self.query_one("#search-bar")
        bar.remove_class("visible")
        if clear:
            self._apply_filter("")
        # Restore focus to last-targeted pane
        if self._search_target:
            self._focus_pane(self._search_target)

    def _render_overlay(self) -> None:
        # Remove any existing overlay
        for w in list(self.query("HelpOverlay, OwnerOverlay")):
            w.remove()
        if self.show_help:
            self.mount(HelpOverlay(id="help"))
        elif self.show_owner:
            ovr = OwnerOverlay(id="help")
            self.mount(ovr)

            def _populate() -> None:
                tbl = self.query_one("#owner-table", DataTable)
                tbl.add_columns("owner", "deals", "$ARR")
                for o in self.owners or []:
                    tbl.add_row(
                        o.get("owner", "—"),
                        str(o.get("deal_count", 0)),
                        _fmt_money(o.get("total_arr", 0)),
                    )
                if not self.owners:
                    tbl.add_row("(no data — refresh in live mode)", "", "")

            self.call_after_refresh(_populate)

    def _toast(self, msg: str, kind: str = "info") -> None:
        t = self.query_one("#toast", Static)
        t.update(msg)
        t.remove_class("error")
        if kind == "error":
            t.add_class("error")
        t.add_class("visible")
        self.set_timer(3.5, lambda: t.remove_class("visible"))


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Sales Ops Cockpit (Textual TUI).")
    p.add_argument(
        "--no-fetch", action="store_true", help="skip live SF pull; load cached snapshot"
    )
    args = p.parse_args(argv)
    Cockpit(fetch_live=not args.no_fetch).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
