"""
Aegis Command Center — Native macOS App
Connects to the Render API and provides a real-time dark dashboard.

Install deps once:  pip3 install customtkinter
Run:                python3 aegis_mac_app.py
"""
import threading
import time
import json
import urllib.request
import urllib.error
from datetime import datetime

try:
    import customtkinter as ctk
except ImportError:
    import subprocess, sys
    print("Installation de customtkinter...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter", "-q"])
    import customtkinter as ctk

# ── API Target ─────────────────────────────────────────────────
API_BASE = "https://aegis-trader.onrender.com"

# ── Palette ────────────────────────────────────────────────────
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
BLUE    = "#7aa2f7"
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


# ── App ────────────────────────────────────────────────────────

class AegisApp(ctk.CTk):

    REFRESH_SEC = 5

    def __init__(self):
        super().__init__()
        self.title("⚡  AEGIS — Command Center")
        self.geometry("1420x860")
        self.minsize(1100, 700)
        self.configure(fg_color=BG)

        self._data: dict      = {}
        self._connected: bool = False
        self._countdown: int  = self.REFRESH_SEC
        self._scanning: bool  = False

        self._build_ui()
        self._start_bg_refresh()
        self._tick()

    # ── Layout helpers ─────────────────────────────────────────

    def _card(self, parent, title: str, row: int, col: int,
              rowspan: int = 1, colspan: int = 1) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=10,
                         border_width=1, border_color=BORDER)
        f.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan,
               padx=6, pady=6, sticky="nsew")
        ctk.CTkLabel(f, text=title,
                     font=ctk.CTkFont("Courier New", 11, "bold"),
                     text_color=DIM).pack(anchor="w", padx=16, pady=(13, 4))
        return f

    def _sep(self, parent) -> ctk.CTkFrame:
        return ctk.CTkFrame(parent, height=1, fg_color=BORDER)

    # ── Full UI build ──────────────────────────────────────────

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0, height=56)
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
        self._lbl_tick.pack(side="right", padx=6)

        # ── Body grid ─────────────────────────────────────────
        body = ctk.CTkFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=12, pady=10)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=0)
        body.rowconfigure(1, weight=1)
        body.rowconfigure(2, weight=0)

        self._build_agents(body)
        self._build_portfolio(body)
        self._build_scan(body)
        self._build_trades(body)
        self._build_actions(body)

    # ── Panel: Agents ──────────────────────────────────────────

    def _build_agents(self, parent):
        card = self._card(parent, "⬡  AGENTS", 0, 0)
        row  = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 14))
        row.columnconfigure((0, 1, 2, 3), weight=1)

        self._agent_widgets: dict = {}
        for i, name in enumerate(["MACRO", "SIGNAL", "EXEC", "TELEGRAM"]):
            box = ctk.CTkFrame(row, fg_color=ROW_ALT, corner_radius=7)
            box.grid(row=0, column=i, padx=4, pady=4, sticky="ew")

            ctk.CTkLabel(box, text=name,
                         font=ctk.CTkFont("Courier New", 10, "bold"),
                         text_color=DIM).pack(pady=(11, 2))

            lbl_s = ctk.CTkLabel(box, text="○  OFFLINE",
                                 font=ctk.CTkFont("Courier New", 11, "bold"),
                                 text_color=RED)
            lbl_s.pack(pady=1)

            lbl_m = ctk.CTkLabel(box, text="—",
                                 font=ctk.CTkFont("Courier New", 9),
                                 text_color=DIM, wraplength=130)
            lbl_m.pack(pady=(1, 11))

            self._agent_widgets[name] = (lbl_s, lbl_m)

    # ── Panel: Portfolio ───────────────────────────────────────

    def _build_portfolio(self, parent):
        card = self._card(parent, "💼  PORTFOLIO", 0, 1)

        metrics_row = ctk.CTkFrame(card, fg_color="transparent")
        metrics_row.pack(fill="x", padx=16, pady=(0, 8))
        metrics_row.columnconfigure((0, 1, 2, 3), weight=1)

        self._metric_labels: dict = {}
        specs = [
            ("EQUITY",    "—", CYAN),
            ("CASH",      "—", TEXT),
            ("P&L TOTAL", "—", GREEN),
            ("WIN RATE",  "—", YELLOW),
        ]
        for i, (label, val, color) in enumerate(specs):
            box = ctk.CTkFrame(metrics_row, fg_color=ROW_ALT, corner_radius=7)
            box.grid(row=0, column=i, padx=4, pady=4, sticky="ew")

            ctk.CTkLabel(box, text=label,
                         font=ctk.CTkFont("Courier New", 9),
                         text_color=DIM).pack(pady=(10, 2))

            lbl = ctk.CTkLabel(box, text=val,
                               font=ctk.CTkFont("Courier New", 15, "bold"),
                               text_color=color)
            lbl.pack(pady=(0, 10))
            self._metric_labels[label] = lbl

        sub = ctk.CTkFrame(card, fg_color="transparent")
        sub.pack(fill="x", padx=16, pady=(0, 4))

        self._lbl_open_pos = ctk.CTkLabel(sub, text="Positions ouvertes : 0",
                                          font=ctk.CTkFont("Courier New", 11),
                                          text_color=DIM)
        self._lbl_open_pos.pack(side="left")

        self._lbl_total_trades = ctk.CTkLabel(sub, text="Total trades : 0",
                                              font=ctk.CTkFont("Courier New", 11),
                                              text_color=DIM)
        self._lbl_total_trades.pack(side="right")

        self._lbl_flag = ctk.CTkLabel(card, text="▶  TRADING ACTIF",
                                      font=ctk.CTkFont("Courier New", 13, "bold"),
                                      text_color=GREEN)
        self._lbl_flag.pack(padx=16, pady=(4, 14))

    # ── Panel: Scan ────────────────────────────────────────────

    def _build_scan(self, parent):
        card = self._card(parent, "📡  DERNIER SCAN MARCHÉ", 1, 0)

        self._lbl_scan_ts = ctk.CTkLabel(card, text="Aucun scan enregistré",
                                         font=ctk.CTkFont("Courier New", 10),
                                         text_color=DIM)
        self._lbl_scan_ts.pack(padx=16, pady=(0, 6))

        # Table header
        hdr = ctk.CTkFrame(card, fg_color=ROW_ALT, corner_radius=0)
        hdr.pack(fill="x", padx=16)
        for txt, w in [("ASSET", 90), ("PRIX", 100), ("RSI", 55), ("TREND", 90), ("BIAS", 90)]:
            ctk.CTkLabel(hdr, text=txt,
                         font=ctk.CTkFont("Courier New", 9, "bold"),
                         text_color=DIM, width=w).pack(side="left", padx=4, pady=5)

        self._scan_body = ctk.CTkFrame(card, fg_color="transparent")
        self._scan_body.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    # ── Panel: Trades ──────────────────────────────────────────

    def _build_trades(self, parent):
        card = self._card(parent, "📊  DERNIERS TRADES", 1, 1)

        self._trades_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self._trades_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 14))

    # ── Panel: Actions ─────────────────────────────────────────

    def _build_actions(self, parent):
        bar = ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=10, height=72)
        bar.grid(row=2, column=0, columnspan=2, padx=6, pady=6, sticky="ew")
        bar.pack_propagate(False)

        btn_kw = dict(font=ctk.CTkFont("Courier New", 12, "bold"),
                      corner_radius=7, width=165, height=44)

        self._btn_toggle = ctk.CTkButton(
            bar, text="⏸  PAUSE BOT",
            fg_color=RED, hover_color="#cc2222",
            command=self._on_toggle, **btn_kw)
        self._btn_toggle.pack(side="left", padx=16, pady=14)

        self._btn_scan = ctk.CTkButton(
            bar, text="🔍  SCAN NOW",
            fg_color="#1a3a5c", hover_color="#0d2a4a",
            command=self._on_scan, **btn_kw)
        self._btn_scan.pack(side="left", padx=6, pady=14)

        ctk.CTkButton(
            bar, text="↻  REFRESH",
            fg_color="#1a2a3a", hover_color="#0d1a2a",
            command=self._on_force_refresh, **btn_kw).pack(side="left", padx=6, pady=14)

        self._lbl_action = ctk.CTkLabel(bar, text="",
                                        font=ctk.CTkFont("Courier New", 11),
                                        text_color=GREEN)
        self._lbl_action.pack(side="left", padx=16)

    # ── Background refresh loop ────────────────────────────────

    def _start_bg_refresh(self):
        def loop():
            while True:
                self._fetch()
                for i in range(self.REFRESH_SEC, 0, -1):
                    self._countdown = i
                    time.sleep(1)
        threading.Thread(target=loop, daemon=True).start()

    def _tick(self):
        self._lbl_tick.configure(text=f"↻ {self._countdown}s")
        self.after(1000, self._tick)

    def _fetch(self):
        try:
            self._data = {
                "state":     _get("/api/state"),
                "portfolio": _get("/api/portfolio"),
                "scan":      _get("/api/scan"),
            }
            self._connected = True
            self.after(0, self._refresh_ui)
        except Exception:
            self._connected = False
            self.after(0, lambda: self._lbl_status.configure(
                text="● HORS LIGNE", text_color=RED))

    # ── UI refresh (main thread) ───────────────────────────────

    def _refresh_ui(self):
        now = datetime.now().strftime("%H:%M:%S")
        self._lbl_status.configure(
            text=f"● CONNECTÉ  {now}" if self._connected else "● HORS LIGNE",
            text_color=GREEN if self._connected else RED)

        self._update_agents()
        self._update_portfolio()
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
        pnl   = port.get("total_pnl",  0)
        wr    = port.get("win_rate",    0)
        total = port.get("total_trades", 0)
        eq    = snap.get("total_equity", 0)
        cash  = snap.get("cash",         0)

        self._metric_labels["EQUITY"].configure(
            text=f"${eq:,.0f}" if eq else "—", text_color=CYAN)
        self._metric_labels["CASH"].configure(
            text=f"${cash:,.0f}" if cash else "—")
        sign = "+" if pnl >= 0 else ""
        self._metric_labels["P&L TOTAL"].configure(
            text=f"{sign}${pnl:,.2f}" if total else "—",
            text_color=(GREEN if pnl >= 0 else RED))
        self._metric_labels["WIN RATE"].configure(
            text=f"{wr}%" if total else "—",
            text_color=(GREEN if wr >= 60 else YELLOW if wr >= 45 else RED))

        open_t = port.get("open_trades", [])
        self._lbl_open_pos.configure(text=f"Positions ouvertes : {len(open_t)}")
        self._lbl_total_trades.configure(text=f"Total trades : {total}")

        scan    = self._data.get("scan", {})
        active  = scan.get("trading_active", True)
        ks      = scan.get("kill_switch", False)

        if ks:
            self._lbl_flag.configure(text="⛔  KILL SWITCH ACTIF", text_color=RED)
            self._btn_toggle.configure(state="disabled")
        elif active:
            self._lbl_flag.configure(text="▶  TRADING ACTIF", text_color=GREEN)
            self._btn_toggle.configure(
                text="⏸  PAUSE BOT", fg_color=RED, hover_color="#cc2222",
                state="normal")
        else:
            self._lbl_flag.configure(text="⏸  TRADING SUSPENDU", text_color=ORANGE)
            self._btn_toggle.configure(
                text="▶  REPRENDRE", fg_color="#00aa44", hover_color="#008833",
                state="normal")

    def _update_scan(self):
        scan   = self._data.get("scan", {})
        last   = scan.get("last_scan", {})
        ts     = last.get("timestamp", "Aucun scan enregistré")
        assets = last.get("assets", {})

        self._lbl_scan_ts.configure(text=f"Dernier scan : {ts}")

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
            rsi_color = (RED if rsi > 70 else GREEN if rsi < 30 else TEXT)
            bg_row  = PANEL if idx % 2 == 0 else ROW_ALT

            row = ctk.CTkFrame(self._scan_body, fg_color=bg_row, corner_radius=4)
            row.pack(fill="x", pady=1)

            for txt, color, w in [
                (asset,              TEXT,      90),
                (f"${price:,.1f}",   CYAN,     100),
                (str(int(rsi)),      rsi_color,  55),
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
            pnl_v   = t.get("pnl", 0) or 0
            sign    = "+" if pnl_v >= 0 else ""
            color   = GREEN if pnl_v >= 0 else RED
            emoji   = "✅" if pnl_v >= 0 else "❌"
            date    = (t.get("closed_at") or "—")[:10]
            bg_row  = PANEL if idx % 2 == 0 else ROW_ALT

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

            ctk.CTkLabel(row,
                         text=date,
                         font=ctk.CTkFont("Courier New", 10),
                         text_color=DIM).pack(side="right", padx=14)

    # ── Button actions ─────────────────────────────────────────

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
                    self._fetch(),
                ))
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
    app = AegisApp()
    app.mainloop()
