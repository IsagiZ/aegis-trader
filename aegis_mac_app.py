"""
Aegis Command Center — Native macOS App
Connects to the Render API for real-time trading data.

Install once:  pip3 install customtkinter
Run:           python3 aegis_mac_app.py
"""
import threading
import time
import json
import urllib.request
from datetime import datetime

try:
    import customtkinter as ctk
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter", "-q"])
    import customtkinter as ctk

# ── Config ─────────────────────────────────────────────────────
API_BASE    = "https://aegis-trader.onrender.com"
REFRESH_SEC = 5

# ── Dark palette ───────────────────────────────────────────────
BG      = "#060b14"
PANEL   = "#0d1117"
BORDER  = "#1e2a3a"
ROW_ALT = "#0a0f1a"
TEXT    = "#c0caf5"
DIM     = "#4a5568"
GREEN   = "#00ff88"
YELLOW  = "#ffd700"
RED     = "#ff4444"
ORANGE  = "#ff9e64"
CYAN    = "#7dcfff"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


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


# ── Main app ───────────────────────────────────────────────────

class AegisApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("⚡  AEGIS — Command Center")
        self.geometry("1440x920")
        self.minsize(1100, 750)
        self.configure(fg_color=BG)

        self._data: dict      = {}
        self._connected       = False
        self._countdown       = REFRESH_SEC
        self._scanning        = False

        self._build_ui()
        self._start_bg_refresh()
        self._tick()

    # ── Card helper ────────────────────────────────────────────

    def _card(self, parent, title: str, row: int, col: int,
              rowspan: int = 1, colspan: int = 1) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=10,
                         border_width=1, border_color=BORDER)
        f.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan,
               padx=6, pady=5, sticky="nsew")
        ctk.CTkLabel(f, text=title,
                     font=ctk.CTkFont("Courier New", 11, "bold"),
                     text_color=DIM).pack(anchor="w", padx=16, pady=(12, 3))
        return f

    # ── Full UI ────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=54)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text="⚡  AEGIS  —  COMMAND CENTER",
                     font=ctk.CTkFont("Courier New", 17, "bold"),
                     text_color=CYAN).pack(side="left", padx=24)

        self._lbl_status = ctk.CTkLabel(hdr, text="● CONNEXION...",
                                        font=ctk.CTkFont("Courier New", 12),
                                        text_color=YELLOW)
        self._lbl_status.pack(side="right", padx=24)

        self._lbl_tick = ctk.CTkLabel(hdr, text="",
                                      font=ctk.CTkFont("Courier New", 11),
                                      text_color=DIM)
        self._lbl_tick.pack(side="right", padx=4)

        # Body — 4 rows × 2 columns
        body = ctk.CTkFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=12, pady=8)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=0)   # agents + portfolio
        body.rowconfigure(1, weight=0)   # positions live (full width)
        body.rowconfigure(2, weight=1)   # scan + trades
        body.rowconfigure(3, weight=0)   # actions

        self._build_agents(body)
        self._build_portfolio(body)
        self._build_positions(body)
        self._build_scan(body)
        self._build_trades(body)
        self._build_actions(body)

    # ── Row 0 — Agents ─────────────────────────────────────────

    def _build_agents(self, parent):
        card = self._card(parent, "⬡  AGENTS", 0, 0)
        row  = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 12))
        row.columnconfigure((0, 1, 2, 3), weight=1)

        self._agent_widgets: dict = {}
        for i, name in enumerate(["MACRO", "SIGNAL", "EXEC", "TELEGRAM"]):
            box = ctk.CTkFrame(row, fg_color=ROW_ALT, corner_radius=7)
            box.grid(row=0, column=i, padx=4, pady=2, sticky="ew")

            ctk.CTkLabel(box, text=name,
                         font=ctk.CTkFont("Courier New", 10, "bold"),
                         text_color=DIM).pack(pady=(10, 2))

            lbl_s = ctk.CTkLabel(box, text="○  OFFLINE",
                                 font=ctk.CTkFont("Courier New", 11, "bold"),
                                 text_color=RED)
            lbl_s.pack(pady=1)

            lbl_m = ctk.CTkLabel(box, text="—",
                                 font=ctk.CTkFont("Courier New", 9),
                                 text_color=DIM, wraplength=130)
            lbl_m.pack(pady=(1, 10))

            self._agent_widgets[name] = (lbl_s, lbl_m)

    # ── Row 0 — Portfolio metrics ──────────────────────────────

    def _build_portfolio(self, parent):
        card = self._card(parent, "💼  PORTFOLIO", 0, 1)

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 8))
        row.columnconfigure((0, 1, 2, 3), weight=1)

        self._metric_labels: dict = {}
        for i, (label, color) in enumerate([
            ("EQUITY",    CYAN),
            ("CASH",      TEXT),
            ("P&L TOTAL", GREEN),
            ("WIN RATE",  YELLOW),
        ]):
            box = ctk.CTkFrame(row, fg_color=ROW_ALT, corner_radius=7)
            box.grid(row=0, column=i, padx=4, pady=2, sticky="ew")
            ctk.CTkLabel(box, text=label,
                         font=ctk.CTkFont("Courier New", 9),
                         text_color=DIM).pack(pady=(9, 2))
            lbl = ctk.CTkLabel(box, text="—",
                               font=ctk.CTkFont("Courier New", 14, "bold"),
                               text_color=color)
            lbl.pack(pady=(0, 9))
            self._metric_labels[label] = lbl

        sub = ctk.CTkFrame(card, fg_color="transparent")
        sub.pack(fill="x", padx=16)

        self._lbl_open_pos = ctk.CTkLabel(sub, text="Positions : 0",
                                          font=ctk.CTkFont("Courier New", 11),
                                          text_color=DIM)
        self._lbl_open_pos.pack(side="left")

        self._lbl_total_trades = ctk.CTkLabel(sub, text="Trades : 0",
                                              font=ctk.CTkFont("Courier New", 11),
                                              text_color=DIM)
        self._lbl_total_trades.pack(side="right")

        self._lbl_flag = ctk.CTkLabel(card, text="▶  TRADING ACTIF",
                                      font=ctk.CTkFont("Courier New", 12, "bold"),
                                      text_color=GREEN)
        self._lbl_flag.pack(padx=16, pady=(6, 12))

    # ── Row 1 — Positions Live (full width) ────────────────────

    def _build_positions(self, parent):
        card = self._card(parent, "📈  POSITIONS LIVE  —  Alpaca temps réel",
                          1, 0, colspan=2)

        # Header row
        hdr = ctk.CTkFrame(card, fg_color=ROW_ALT, corner_radius=4)
        hdr.pack(fill="x", padx=16, pady=(0, 2))
        for txt, w in [("SYMBOL", 90), ("SIDE", 70), ("QTÉ", 60),
                       ("ENTRÉE", 100), ("PRIX ACT.", 100),
                       ("VALEUR", 110), ("P&L NON-RÉALISÉ", 160), ("%", 80)]:
            ctk.CTkLabel(hdr, text=txt,
                         font=ctk.CTkFont("Courier New", 9, "bold"),
                         text_color=DIM, width=w).pack(side="left", padx=5, pady=5)

        self._pos_body = ctk.CTkFrame(card, fg_color="transparent", height=70)
        self._pos_body.pack(fill="x", padx=16, pady=(0, 12))
        self._pos_body.pack_propagate(False)

        # Initial placeholder
        self._lbl_no_pos = ctk.CTkLabel(self._pos_body,
                                        text="Aucune position ouverte en ce moment.",
                                        font=ctk.CTkFont("Courier New", 11),
                                        text_color=DIM)
        self._lbl_no_pos.pack(pady=18)

    # ── Row 2 — Scan ───────────────────────────────────────────

    def _build_scan(self, parent):
        card = self._card(parent, "📡  DERNIER SCAN MARCHÉ", 2, 0)

        self._lbl_scan_ts = ctk.CTkLabel(card, text="Aucun scan",
                                         font=ctk.CTkFont("Courier New", 10),
                                         text_color=DIM)
        self._lbl_scan_ts.pack(padx=16, pady=(0, 4))

        hdr = ctk.CTkFrame(card, fg_color=ROW_ALT, corner_radius=4)
        hdr.pack(fill="x", padx=16)
        for txt, w in [("ASSET", 90), ("PRIX", 100), ("RSI", 55), ("TREND", 90), ("BIAS", 90)]:
            ctk.CTkLabel(hdr, text=txt,
                         font=ctk.CTkFont("Courier New", 9, "bold"),
                         text_color=DIM, width=w).pack(side="left", padx=4, pady=4)

        self._scan_body = ctk.CTkFrame(card, fg_color="transparent")
        self._scan_body.pack(fill="both", expand=True, padx=16, pady=(2, 12))

    # ── Row 2 — Trades ─────────────────────────────────────────

    def _build_trades(self, parent):
        card = self._card(parent, "📊  DERNIERS TRADES FERMÉS", 2, 1)
        self._trades_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self._trades_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    # ── Row 3 — Actions ────────────────────────────────────────

    def _build_actions(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=10, height=68)
        bar.grid(row=3, column=0, columnspan=2, padx=6, pady=5, sticky="ew")
        bar.pack_propagate(False)

        kw = dict(font=ctk.CTkFont("Courier New", 12, "bold"),
                  corner_radius=7, width=165, height=42)

        self._btn_toggle = ctk.CTkButton(
            bar, text="⏸  PAUSE BOT",
            fg_color=RED, hover_color="#cc2222",
            command=self._on_toggle, **kw)
        self._btn_toggle.pack(side="left", padx=16, pady=13)

        self._btn_scan = ctk.CTkButton(
            bar, text="🔍  SCAN NOW",
            fg_color="#1a3a5c", hover_color="#0d2a4a",
            command=self._on_scan, **kw)
        self._btn_scan.pack(side="left", padx=6, pady=13)

        ctk.CTkButton(
            bar, text="↻  REFRESH",
            fg_color="#1a2a3a", hover_color="#0d1a2a",
            command=self._on_force_refresh, **kw).pack(side="left", padx=6, pady=13)

        self._lbl_action = ctk.CTkLabel(bar, text="",
                                        font=ctk.CTkFont("Courier New", 11),
                                        text_color=GREEN)
        self._lbl_action.pack(side="left", padx=16)

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
        self.after(1000, self._tick)

    def _fetch(self):
        try:
            state_data  = _get("/api/state")
            port_data   = _get("/api/portfolio")
            scan_data   = _get("/api/scan")
            pos_data    = _get("/api/positions")
            self._data  = {
                "state":     state_data,
                "portfolio": port_data,
                "scan":      scan_data,
                "positions": pos_data,
            }
            self._connected = True
            self.after(0, self._refresh_ui)
        except Exception:
            self._connected = False
            self.after(0, lambda: self._lbl_status.configure(
                text="● HORS LIGNE", text_color=RED))

    # ── UI update (main thread) ────────────────────────────────

    def _refresh_ui(self):
        now = datetime.now().strftime("%H:%M:%S")
        self._lbl_status.configure(
            text=f"● CONNECTÉ  {now}" if self._connected else "● HORS LIGNE",
            text_color=GREEN if self._connected else RED)

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
            lbl_s.configure(text=f"{sym}  {status}", text_color=color)
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
            text=f"${eq:,.0f}" if eq else "—", text_color=CYAN)
        self._metric_labels["CASH"].configure(
            text=f"${cash:,.0f}" if cash else "—")
        sign = "+" if pnl >= 0 else ""
        self._metric_labels["P&L TOTAL"].configure(
            text=f"{sign}${pnl:,.2f}" if total else "—",
            text_color=GREEN if pnl >= 0 else RED)
        self._metric_labels["WIN RATE"].configure(
            text=f"{wr}%" if total else "—",
            text_color=GREEN if wr >= 60 else YELLOW if wr >= 45 else RED)

        open_t = port.get("open_trades", [])
        self._lbl_open_pos.configure(text=f"Positions : {len(open_t)}")
        self._lbl_total_trades.configure(text=f"Trades : {total}")

        scan   = self._data.get("scan", {})
        active = scan.get("trading_active", True)
        ks     = scan.get("kill_switch",    False)

        if ks:
            self._lbl_flag.configure(text="⛔  KILL SWITCH ACTIF", text_color=RED)
            self._btn_toggle.configure(state="disabled")
        elif active:
            self._lbl_flag.configure(text="▶  TRADING ACTIF",     text_color=GREEN)
            self._btn_toggle.configure(
                text="⏸  PAUSE BOT", fg_color=RED, hover_color="#cc2222", state="normal")
        else:
            self._lbl_flag.configure(text="⏸  TRADING SUSPENDU",  text_color=ORANGE)
            self._btn_toggle.configure(
                text="▶  REPRENDRE", fg_color="#00aa44", hover_color="#008833", state="normal")

    def _update_positions(self):
        pos_data  = self._data.get("positions", {})
        positions = pos_data.get("positions", [])
        total_upl = pos_data.get("total_upl", 0)

        for w in self._pos_body.winfo_children():
            w.destroy()

        if not positions:
            self._pos_body.configure(height=60)
            ctk.CTkLabel(self._pos_body,
                         text="Aucune position ouverte en ce moment.",
                         font=ctk.CTkFont("Courier New", 11),
                         text_color=DIM).pack(pady=16)
            return

        # Resize body to fit rows
        self._pos_body.configure(height=max(60, len(positions) * 38 + 4))

        for idx, p in enumerate(positions):
            upl   = p.get("unrealized_pl",  0)
            uplpc = p.get("unrealized_plpc", 0) * 100
            side  = str(p.get("side", "")).replace("PositionSide.", "").upper()
            bg    = PANEL if idx % 2 == 0 else ROW_ALT

            row = ctk.CTkFrame(self._pos_body, fg_color=bg, corner_radius=4)
            row.pack(fill="x", pady=1)

            pnl_color = GREEN if upl >= 0 else RED
            sign      = "+" if upl >= 0 else ""
            side_col  = GREEN if side == "LONG" else RED

            for txt, color, w in [
                (p.get("symbol", "?"),           TEXT,      90),
                (side,                            side_col,  70),
                (str(int(p.get("qty", 0))),       DIM,       60),
                (f"${p.get('avg_entry', 0):,.2f}", DIM,     100),
                (f"${p.get('current_price',0):,.2f}", CYAN,  100),
                (f"${p.get('market_value',0):,.0f}", TEXT,   110),
                (f"{sign}${upl:,.2f}",            pnl_color, 160),
                (f"{sign}{uplpc:.1f}%",            pnl_color,  80),
            ]:
                ctk.CTkLabel(row, text=txt,
                             font=ctk.CTkFont("Courier New", 11, "bold" if w == 90 else "normal"),
                             text_color=color, width=w).pack(side="left", padx=5, pady=7)

        # Summary line
        if len(positions) > 1:
            summary = ctk.CTkFrame(self._pos_body, fg_color="transparent")
            summary.pack(fill="x", pady=(2, 0))
            sign = "+" if total_upl >= 0 else ""
            ctk.CTkLabel(summary,
                         text=f"P&L non-réalisé total : {sign}${total_upl:,.2f}",
                         font=ctk.CTkFont("Courier New", 11, "bold"),
                         text_color=GREEN if total_upl >= 0 else RED).pack(
                side="right", padx=8, pady=2)

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

            t_sym   = "▲" if trend == "bull" else "▼" if trend == "bear" else "→"
            t_color = GREEN if trend == "bull" else RED if trend == "bear" else YELLOW
            b_color = GREEN if "bull" in str(bias) else RED if "bear" in str(bias) else YELLOW
            rsi_c   = RED if rsi > 70 else GREEN if rsi < 30 else TEXT
            bg_row  = PANEL if idx % 2 == 0 else ROW_ALT

            row = ctk.CTkFrame(self._scan_body, fg_color=bg_row, corner_radius=4)
            row.pack(fill="x", pady=1)

            for txt, color, w in [
                (asset,              TEXT,       90),
                (f"${price:,.1f}",   CYAN,      100),
                (str(int(rsi)),      rsi_c,      55),
                (f"{t_sym} {trend}", t_color,    90),
                (str(bias),          b_color,    90),
            ]:
                ctk.CTkLabel(row, text=txt,
                             font=ctk.CTkFont("Courier New", 11),
                             text_color=color, width=w).pack(
                    side="left", padx=4, pady=6)

    def _update_trades(self):
        for w in self._trades_scroll.winfo_children():
            w.destroy()

        port   = self._data.get("portfolio", {})
        closed = port.get("closed_trades", [])

        if not closed:
            ctk.CTkLabel(self._trades_scroll,
                         text="Aucun trade fermé pour l'instant.",
                         font=ctk.CTkFont("Courier New", 11),
                         text_color=DIM).pack(pady=24)
            return

        for idx, t in enumerate(reversed(closed)):
            pnl_v  = t.get("pnl", 0) or 0
            sign   = "+" if pnl_v >= 0 else ""
            color  = GREEN if pnl_v >= 0 else RED
            emoji  = "✅" if pnl_v >= 0 else "❌"
            date   = (t.get("closed_at") or "—")[:10]
            bg_row = PANEL if idx % 2 == 0 else ROW_ALT

            row = ctk.CTkFrame(self._trades_scroll, fg_color=bg_row, corner_radius=5)
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row,
                         text=f"{emoji}  {t.get('asset','?')}  "
                              f"{(t.get('direction') or '').upper()}",
                         font=ctk.CTkFont("Courier New", 11, "bold"),
                         text_color=TEXT).pack(side="left", padx=14, pady=7)

            ctk.CTkLabel(row,
                         text=f"{sign}${pnl_v:.2f}",
                         font=ctk.CTkFont("Courier New", 12, "bold"),
                         text_color=color).pack(side="left", padx=8)

            ctk.CTkLabel(row, text=date,
                         font=ctk.CTkFont("Courier New", 10),
                         text_color=DIM).pack(side="right", padx=14)

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
                self.after(0, lambda: (
                    self._lbl_action.configure(text=f"✓  {msg}", text_color=GREEN),
                    self._btn_toggle.configure(state="normal"),
                ))
                self._fetch()
            except Exception as e:
                self.after(0, lambda: (
                    self._lbl_action.configure(text=f"❌  {e}", text_color=RED),
                    self._btn_toggle.configure(state="normal"),
                ))
        threading.Thread(target=do, daemon=True).start()

    def _on_scan(self):
        if self._scanning:
            return
        self._scanning = True
        self._btn_scan.configure(state="disabled", text="⟳  SCAN...")
        self._lbl_action.configure(text="⟳  Scan en cours...", text_color=YELLOW)

        def do():
            try:
                res = _post("/api/command", {"cmd": "scan"})
                msg = res.get("msg", "OK")
                self.after(0, lambda: self._lbl_action.configure(
                    text=f"✓  {msg}", text_color=GREEN))
                self._fetch()
            except Exception as e:
                self.after(0, lambda: self._lbl_action.configure(
                    text=f"❌  {e}", text_color=RED))
            finally:
                self._scanning = False
                self.after(0, lambda: self._btn_scan.configure(
                    state="normal", text="🔍  SCAN NOW"))
        threading.Thread(target=do, daemon=True).start()

    def _on_force_refresh(self):
        self._countdown = 1
        threading.Thread(target=self._fetch, daemon=True).start()


# ── Entry point ────────────────────────────────────────────────

if __name__ == "__main__":
    AegisApp().mainloop()
