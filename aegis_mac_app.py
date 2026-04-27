"""
Aegis Command Center — Native macOS App
Uses only stdlib tkinter — no external dependencies required.

Run:  python3 aegis_mac_app.py
"""
import tkinter as tk
from tkinter import ttk
import threading
import time
import json
import urllib.request
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────
API_BASE    = "https://aegis-trader.onrender.com"
REFRESH_SEC = 5

# ── Palette ────────────────────────────────────────────────────
BG      = "#060b14"
PANEL   = "#0d1117"
BORDER  = "#1a2540"
ROW1    = "#0d1117"
ROW2    = "#0a0f1a"
TEXT    = "#c0caf5"
DIM     = "#4a5568"
GREEN   = "#00cc66"
YELLOW  = "#e6c200"
RED     = "#e03030"
ORANGE  = "#e07a20"
CYAN    = "#5fb8d4"
FONT    = "Courier"


# ── HTTP helpers ───────────────────────────────────────────────

def _get(path: str) -> dict:
    req = urllib.request.Request(f"{API_BASE}{path}")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def _post(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{API_BASE}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


# ── Scrollable frame helper ─────────────────────────────────────

class ScrollFrame(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=kw.pop("bg", PANEL))
        self.canvas = tk.Canvas(self, bg=kw.pop("canvas_bg", PANEL),
                                highlightthickness=0, **kw)
        self.scroll  = tk.Scrollbar(self, orient="vertical",
                                    command=self.canvas.yview)
        self.inner   = tk.Frame(self.canvas, bg=self.canvas["bg"])
        self._win_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_inner_configure(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self._win_id, width=event.width)


# ── Main app ───────────────────────────────────────────────────

class AegisApp:

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("⚡  AEGIS — Command Center")
        self.root.geometry("1400x900")
        self.root.minsize(1100, 750)
        self.root.configure(bg=BG)

        # Set dark title bar (macOS)
        try:
            self.root.tk.call("::tk::unsupported::MacWindowStyle", "style",
                              self.root._w, "document", "none")
        except Exception:
            pass

        self._data:      dict = {}
        self._connected: bool = False
        self._countdown: int  = REFRESH_SEC
        self._scanning:  bool = False

        self._build_ui()
        self._start_bg_refresh()
        self._tick()

    def run(self):
        self.root.mainloop()

    # ── Convenience widget factories ───────────────────────────

    def _lbl(self, parent, text="", fg=TEXT, size=11, bold=False,
             anchor="w", **kw) -> tk.Label:
        weight = "bold" if bold else "normal"
        return tk.Label(parent, text=text, fg=fg,
                        bg=kw.pop("bg", parent["bg"]),
                        font=(FONT, size, weight), anchor=anchor, **kw)

    def _btn(self, parent, text, command, fg=TEXT,
             bg="#1a3a5c", abg="#0d2a4a", w=16) -> tk.Label:
        """Button implemented as a styled Label (no native macOS chrome)."""
        b = tk.Label(parent, text=text, fg=fg, bg=bg,
                     font=(FONT, 11, "bold"), padx=14, pady=8,
                     cursor="hand2", relief="flat", width=w)
        b.bind("<Button-1>",       lambda _: command())
        b.bind("<Enter>",          lambda _: b.configure(bg=abg))
        b.bind("<Leave>",          lambda _: b.configure(bg=bg))
        b._default_bg = bg
        b._active_bg  = abg
        return b

    def _section(self, parent, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=PANEL,
                         highlightbackground=BORDER, highlightthickness=1)
        tk.Label(outer, text=title, fg=DIM, bg=PANEL,
                 font=(FONT, 10, "bold")).pack(anchor="w", padx=14, pady=(10, 3))
        return outer

    def _hdiv(self, parent) -> tk.Frame:
        return tk.Frame(parent, bg=BORDER, height=1)

    # ── Full UI build ──────────────────────────────────────────

    def _build_ui(self):
        r = self.root

        # ── Header ────────────────────────────────────────────
        hdr = tk.Frame(r, bg=PANEL, height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self._lbl(hdr, "⚡  AEGIS  —  COMMAND CENTER",
                  fg=CYAN, size=16, bold=True).pack(side="left", padx=22)

        self._lbl_tick = self._lbl(hdr, "", fg=DIM, size=10)
        self._lbl_tick.pack(side="right", padx=8)

        self._lbl_status = self._lbl(hdr, "● CONNEXION...", fg=YELLOW, size=11)
        self._lbl_status.pack(side="right", padx=16)

        # ── Body ──────────────────────────────────────────────
        body = tk.Frame(r, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=8)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(2, weight=1)

        self._build_agents(body)
        self._build_portfolio(body)
        self._build_positions(body)
        self._build_scan(body)
        self._build_trades(body)
        self._build_actions(body)

    # ── Row 0 — Agents (left) ──────────────────────────────────

    def _build_agents(self, parent):
        sec = self._section(parent, "⬡  AGENTS")
        sec.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        row = tk.Frame(sec, bg=PANEL)
        row.pack(fill="x", padx=12, pady=(0, 12))
        for i in range(4):
            row.columnconfigure(i, weight=1)

        self._agent_widgets: dict = {}
        for i, name in enumerate(["MACRO", "SIGNAL", "EXEC", "TELEGRAM"]):
            box = tk.Frame(row, bg=ROW2,
                           highlightbackground=BORDER, highlightthickness=1)
            box.grid(row=0, column=i, padx=3, pady=3, sticky="ew")

            self._lbl(box, name, fg=DIM, size=9, bold=True, bg=ROW2,
                      anchor="center").pack(pady=(9, 2), padx=6)

            lbl_s = self._lbl(box, "○  OFFLINE", fg=RED, size=10, bold=True,
                              bg=ROW2, anchor="center")
            lbl_s.pack(pady=1)

            lbl_m = self._lbl(box, "—", fg=DIM, size=8, bg=ROW2,
                              anchor="center", wraplength=120)
            lbl_m.pack(pady=(1, 9), padx=4)

            self._agent_widgets[name] = (lbl_s, lbl_m)

    # ── Row 0 — Portfolio (right) ──────────────────────────────

    def _build_portfolio(self, parent):
        sec = self._section(parent, "💼  PORTFOLIO")
        sec.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        row = tk.Frame(sec, bg=PANEL)
        row.pack(fill="x", padx=12, pady=(0, 6))
        for i in range(4):
            row.columnconfigure(i, weight=1)

        self._metric_labels: dict = {}
        for i, (label, color) in enumerate([
            ("EQUITY",    CYAN),
            ("CASH",      TEXT),
            ("P&L TOTAL", GREEN),
            ("WIN RATE",  YELLOW),
        ]):
            box = tk.Frame(row, bg=ROW2,
                           highlightbackground=BORDER, highlightthickness=1)
            box.grid(row=0, column=i, padx=3, pady=3, sticky="ew")
            self._lbl(box, label, fg=DIM, size=8, bg=ROW2, anchor="center").pack(
                pady=(8, 2))
            lbl = self._lbl(box, "—", fg=color, size=14, bold=True,
                            bg=ROW2, anchor="center")
            lbl.pack(pady=(0, 8))
            self._metric_labels[label] = lbl

        sub = tk.Frame(sec, bg=PANEL)
        sub.pack(fill="x", padx=14, pady=(0, 2))

        self._lbl_open_pos = self._lbl(sub, "Positions : 0", fg=DIM, size=10)
        self._lbl_open_pos.pack(side="left")

        self._lbl_total_trades = self._lbl(sub, "Trades : 0", fg=DIM, size=10)
        self._lbl_total_trades.pack(side="right")

        self._lbl_flag = self._lbl(sec, "▶  TRADING ACTIF",
                                   fg=GREEN, size=12, bold=True, anchor="center")
        self._lbl_flag.pack(pady=(4, 12))

    # ── Row 1 — Positions Live (full width) ────────────────────

    def _build_positions(self, parent):
        sec = self._section(parent, "📈  POSITIONS LIVE  —  Alpaca temps réel")
        sec.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # Table header
        hdr = tk.Frame(sec, bg=ROW2)
        hdr.pack(fill="x", padx=12, pady=(0, 2))
        for txt, w in [("SYMBOL", 8), ("SIDE", 6), ("QTÉ", 5),
                       ("ENTRÉE", 10), ("PRIX ACT.", 10),
                       ("VALEUR", 10), ("P&L NON-RÉALISÉ", 16), ("%", 7)]:
            self._lbl(hdr, txt, fg=DIM, size=9, bold=True,
                      bg=ROW2, width=w, anchor="center").pack(
                side="left", padx=4, pady=4)

        self._pos_frame = tk.Frame(sec, bg=PANEL, height=56)
        self._pos_frame.pack(fill="x", padx=12, pady=(0, 10))
        self._pos_frame.pack_propagate(False)

        self._lbl_no_pos = self._lbl(
            self._pos_frame, "Aucune position ouverte en ce moment.",
            fg=DIM, size=10, anchor="center")
        self._lbl_no_pos.pack(pady=14)

    # ── Row 2 — Scan (left) ────────────────────────────────────

    def _build_scan(self, parent):
        sec = self._section(parent, "📡  DERNIER SCAN MARCHÉ")
        sec.grid(row=2, column=0, padx=5, pady=5, sticky="nsew")

        self._lbl_scan_ts = self._lbl(sec, "Aucun scan", fg=DIM, size=9)
        self._lbl_scan_ts.pack(padx=14, pady=(0, 4))

        # Table header
        hdr = tk.Frame(sec, bg=ROW2)
        hdr.pack(fill="x", padx=12)
        for txt, w in [("ASSET", 7), ("PRIX", 9), ("RSI", 5),
                       ("TREND", 8), ("BIAS", 8)]:
            self._lbl(hdr, txt, fg=DIM, size=9, bold=True,
                      bg=ROW2, width=w, anchor="center").pack(
                side="left", padx=3, pady=3)

        self._scan_body = tk.Frame(sec, bg=PANEL)
        self._scan_body.pack(fill="both", expand=True, padx=12, pady=(2, 10))

    # ── Row 2 — Trades (right) ────────────────────────────────

    def _build_trades(self, parent):
        sec = self._section(parent, "📊  DERNIERS TRADES FERMÉS")
        sec.grid(row=2, column=1, padx=5, pady=5, sticky="nsew")

        self._trades_sf = ScrollFrame(sec, bg=PANEL, canvas_bg=PANEL)
        self._trades_sf.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    # ── Row 3 — Actions ────────────────────────────────────────

    def _build_actions(self, parent):
        bar = tk.Frame(parent, bg=PANEL,
                       highlightbackground=BORDER, highlightthickness=1,
                       height=62)
        bar.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
        bar.pack_propagate(False)

        inner = tk.Frame(bar, bg=PANEL)
        inner.pack(side="left", padx=14, pady=10)

        self._btn_toggle = self._btn(
            inner, "⏸  PAUSE BOT", self._on_toggle, fg="white", bg=RED, abg="#aa1a1a")
        self._btn_toggle.pack(side="left", padx=(0, 8))

        self._btn_scan = self._btn(
            inner, "🔍  SCAN NOW", self._on_scan)
        self._btn_scan.pack(side="left", padx=(0, 8))

        self._btn(inner, "↻  REFRESH", self._on_force_refresh,
                  bg="#1a2a3a", abg="#0d1a2a").pack(side="left")

        self._lbl_action = self._lbl(bar, "", fg=GREEN, size=11)
        self._lbl_action.pack(side="left", padx=18)

    # ── Background refresh ─────────────────────────────────────

    def _start_bg_refresh(self):
        def loop():
            while True:
                self._fetch()
                for i in range(REFRESH_SEC, 0, -1):
                    self._countdown = i
                    time.sleep(1)
        threading.Thread(target=loop, daemon=True).start()

    def _tick(self):
        self._lbl_tick.configure(text=f"↻ {self._countdown}s")
        self.root.after(1000, self._tick)

    def _fetch(self):
        try:
            self._data = {
                "state":     _get("/api/state"),
                "portfolio": _get("/api/portfolio"),
                "scan":      _get("/api/scan"),
                "positions": _get("/api/positions"),
            }
            self._connected = True
            self.root.after(0, self._refresh_ui)
        except Exception:
            self._connected = False
            self.root.after(0, lambda: self._lbl_status.configure(
                text="● HORS LIGNE", fg=RED))

    # ── UI update ──────────────────────────────────────────────

    def _refresh_ui(self):
        now = datetime.now().strftime("%H:%M:%S")
        self._lbl_status.configure(
            text=f"● CONNECTÉ  {now}" if self._connected else "● HORS LIGNE",
            fg=GREEN if self._connected else RED)
        self._update_agents()
        self._update_portfolio()
        self._update_positions()
        self._update_scan()
        self._update_trades()

    def _update_agents(self):
        agents = self._data.get("state", {}).get("agents", {})
        for name, (lbl_s, lbl_m) in self._agent_widgets.items():
            info   = agents.get(name, {})
            status = info.get("status", "OFFLINE")
            msg    = (info.get("message") or "")[:32]
            if status == "ACTIVE":
                color, sym = GREEN,  "●"
            elif status == "IDLE":
                color, sym = YELLOW, "◉"
            elif status == "ERROR":
                color, sym = ORANGE, "●"
            else:
                color, sym = RED,    "○"
            lbl_s.configure(text=f"{sym}  {status}", fg=color)
            lbl_m.configure(text=msg or "—")

    def _update_portfolio(self):
        port  = self._data.get("portfolio", {})
        snap  = port.get("portfolio", {})
        pnl   = port.get("total_pnl",    0)
        wr    = port.get("win_rate",      0)
        total = port.get("total_trades",  0)
        eq    = snap.get("total_equity",  0)
        cash  = snap.get("cash",          0)

        self._metric_labels["EQUITY"].configure(
            text=f"${eq:,.0f}" if eq else "—", fg=CYAN)
        self._metric_labels["CASH"].configure(
            text=f"${cash:,.0f}" if cash else "—")
        sign = "+" if pnl >= 0 else ""
        self._metric_labels["P&L TOTAL"].configure(
            text=f"{sign}${pnl:,.2f}" if total else "—",
            fg=GREEN if pnl >= 0 else RED)
        self._metric_labels["WIN RATE"].configure(
            text=f"{wr}%" if total else "—",
            fg=GREEN if wr >= 60 else YELLOW if wr >= 45 else RED)

        open_t = port.get("open_trades", [])
        self._lbl_open_pos.configure(text=f"Positions : {len(open_t)}")
        self._lbl_total_trades.configure(text=f"Trades : {total}")

        scan   = self._data.get("scan", {})
        active = scan.get("trading_active", True)
        ks     = scan.get("kill_switch",    False)

        if ks:
            self._lbl_flag.configure(text="⛔  KILL SWITCH ACTIF", fg=RED)
            self._btn_toggle.configure(state="disabled")
        elif active:
            self._lbl_flag.configure(text="▶  TRADING ACTIF", fg=GREEN)
            self._btn_toggle.configure(
                text="⏸  PAUSE BOT", bg=RED,
                state="normal")
            self._btn_toggle._default_bg = RED
        else:
            self._lbl_flag.configure(text="⏸  TRADING SUSPENDU", fg=ORANGE)
            self._btn_toggle.configure(
                text="▶  REPRENDRE", bg="#006633",
                state="normal")
            self._btn_toggle._default_bg = "#006633"

    def _update_positions(self):
        pos_data  = self._data.get("positions", {})
        positions = pos_data.get("positions", [])
        total_upl = pos_data.get("total_upl", 0)

        for w in self._pos_frame.winfo_children():
            w.destroy()

        if not positions:
            self._pos_frame.configure(height=52)
            self._lbl(self._pos_frame, "Aucune position ouverte en ce moment.",
                      fg=DIM, size=10, anchor="center").pack(pady=14)
            return

        row_h = 34
        self._pos_frame.configure(height=len(positions) * row_h + 6)

        for idx, p in enumerate(positions):
            upl    = p.get("unrealized_pl",  0)
            uplpc  = (p.get("unrealized_plpc", 0) or 0) * 100
            side   = str(p.get("side", "")).upper().replace("POSITIONSIDE.", "")
            bg     = ROW1 if idx % 2 == 0 else ROW2
            pcolor = GREEN if upl >= 0 else RED
            scolor = GREEN if "LONG" in side else RED
            sign   = "+" if upl >= 0 else ""

            row = tk.Frame(self._pos_frame, bg=bg)
            row.pack(fill="x", pady=1)

            for txt, color, w in [
                (p.get("symbol", "?"),            TEXT,   8),
                (side,                            scolor, 6),
                (str(int(abs(p.get("qty", 0)))),  DIM,    5),
                (f"${p.get('avg_entry',0):,.2f}", DIM,   10),
                (f"${p.get('current_price',0):,.2f}", CYAN, 10),
                (f"${p.get('market_value',0):,.0f}", TEXT, 10),
                (f"{sign}${upl:,.2f}",            pcolor, 16),
                (f"{sign}{uplpc:.1f}%",            pcolor,  7),
            ]:
                self._lbl(row, txt, fg=color, size=10,
                          bg=bg, width=w, anchor="center").pack(
                    side="left", padx=4, pady=6)

        if len(positions) > 1:
            sign = "+" if total_upl >= 0 else ""
            summary = tk.Frame(self._pos_frame, bg=PANEL)
            summary.pack(fill="x")
            self._lbl(summary,
                      f"P&L non-réalisé total : {sign}${total_upl:,.2f}",
                      fg=GREEN if total_upl >= 0 else RED,
                      size=10, bold=True, anchor="e").pack(
                side="right", padx=10, pady=2)

    def _update_scan(self):
        scan   = self._data.get("scan", {})
        last   = scan.get("last_scan", {})
        ts     = last.get("timestamp",  "Aucun scan")
        assets = last.get("assets",     {})

        self._lbl_scan_ts.configure(text=f"Scan : {ts}")

        for w in self._scan_body.winfo_children():
            w.destroy()

        for idx, (asset, d) in enumerate(assets.items()):
            trend = d.get("trend", "?")
            bias  = d.get("bias",  "?")
            rsi   = d.get("rsi",   0)
            price = d.get("price", 0)
            bg    = ROW1 if idx % 2 == 0 else ROW2

            t_sym   = "▲" if trend == "bull" else "▼" if trend == "bear" else "→"
            t_color = GREEN if trend == "bull" else RED if trend == "bear" else YELLOW
            b_color = GREEN if "bull" in str(bias) else RED if "bear" in str(bias) else YELLOW
            rsi_c   = RED if rsi > 70 else GREEN if rsi < 30 else TEXT

            row = tk.Frame(self._scan_body, bg=bg)
            row.pack(fill="x", pady=1)

            for txt, color, w in [
                (asset,              TEXT,   7),
                (f"${price:,.1f}",   CYAN,   9),
                (str(int(rsi)),      rsi_c,  5),
                (f"{t_sym} {trend}", t_color, 8),
                (str(bias),          b_color, 8),
            ]:
                self._lbl(row, txt, fg=color, size=10,
                          bg=bg, width=w, anchor="center").pack(
                    side="left", padx=3, pady=5)

    def _update_trades(self):
        for w in self._trades_sf.inner.winfo_children():
            w.destroy()

        port   = self._data.get("portfolio", {})
        closed = port.get("closed_trades", [])

        if not closed:
            self._lbl(self._trades_sf.inner,
                      "Aucun trade fermé pour l'instant.",
                      fg=DIM, size=10, anchor="center",
                      bg=self._trades_sf.inner["bg"]).pack(pady=20)
            return

        for idx, t in enumerate(reversed(closed)):
            pnl_v = t.get("pnl", 0) or 0
            sign  = "+" if pnl_v >= 0 else ""
            color = GREEN if pnl_v >= 0 else RED
            emoji = "✅" if pnl_v >= 0 else "❌"
            date  = (t.get("closed_at") or "—")[:10]
            bg    = ROW1 if idx % 2 == 0 else ROW2

            row = tk.Frame(self._trades_sf.inner, bg=bg)
            row.pack(fill="x", pady=1)

            self._lbl(row,
                      f"{emoji}  {t.get('asset','?')}  "
                      f"{(t.get('direction') or '').upper()}",
                      fg=TEXT, size=10, bold=True, bg=bg).pack(
                side="left", padx=12, pady=6)

            self._lbl(row, f"{sign}${pnl_v:.2f}",
                      fg=color, size=11, bold=True, bg=bg).pack(
                side="left", padx=6)

            self._lbl(row, date, fg=DIM, size=9, bg=bg).pack(
                side="right", padx=12)

    # ── Buttons ────────────────────────────────────────────────

    def _on_toggle(self):
        scan   = self._data.get("scan", {})
        active = scan.get("trading_active", True)
        cmd    = "pause" if active else "resume"
        self._btn_toggle.configure(state="disabled")

        def do():
            try:
                res = _post("/api/command", {"cmd": cmd})
                msg = res.get("msg", "OK")
                self.root.after(0, lambda: (
                    self._lbl_action.configure(text=f"✓  {msg}", fg=GREEN),
                    self._btn_toggle.configure(state="normal"),
                ))
                self._fetch()
            except Exception as e:
                self.root.after(0, lambda: (
                    self._lbl_action.configure(text=f"❌  {e}", fg=RED),
                    self._btn_toggle.configure(state="normal"),
                ))
        threading.Thread(target=do, daemon=True).start()

    def _on_scan(self):
        if self._scanning:
            return
        self._scanning = True
        self._btn_scan.configure(state="disabled", text="⟳  SCAN...")
        self._lbl_action.configure(text="⟳  Scan en cours...", fg=YELLOW)

        def do():
            try:
                res = _post("/api/command", {"cmd": "scan"})
                msg = res.get("msg", "OK")
                self.root.after(0, lambda: self._lbl_action.configure(
                    text=f"✓  {msg}", fg=GREEN))
                self._fetch()
            except Exception as e:
                self.root.after(0, lambda: self._lbl_action.configure(
                    text=f"❌  {e}", fg=RED))
            finally:
                self._scanning = False
                self.root.after(0, lambda: self._btn_scan.configure(
                    state="normal", text="🔍  SCAN NOW"))
        threading.Thread(target=do, daemon=True).start()

    def _on_force_refresh(self):
        self._countdown = 1
        threading.Thread(target=self._fetch, daemon=True).start()


# ── Entry point ────────────────────────────────────────────────

if __name__ == "__main__":
    AegisApp().run()
