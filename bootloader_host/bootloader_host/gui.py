"""
Tkinter-based GUI for the STM32F4 Custom Bootloader Host Tool.

Provides a graphical interface over BootloaderClient with:
- COM port / baud rate selection
- Dropdown command selector with descriptions
- Dynamic parameter forms
- Persistent Execute / Cancel action bar
- Progress bar for firmware transfers
- Cooperative cancellation via threading.Event
- Scrolling log output with auto-scroll
- Background threading for responsive UI
"""

from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Any

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

from .client import BootloaderClient, CommandTrace, list_available_ports, DEFAULT_CHUNK_SIZE
from .exceptions import (
    BootloaderError,
    NackError,
    TimeoutError,
    ValidationError,
)
from .protocol import COMMAND_NAMES


# ---------------------------------------------------------------------------
# Internal exception for cooperative cancellation
# ---------------------------------------------------------------------------


class _OperationCancelled(BootloaderError):
    """Raised inside a worker thread when the user clicks Cancel."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BAUD_OPTIONS = [9600, 19200, 38400, 57600, 115200, 230400]
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 2.0
DEFAULT_ADDRESS = "0x08008000"
OTP_BASE_ADDR = 0x1FFF7800
OTP_END_ADDR = 0x1FFF7A10  # 0x1FFF7800 + 528 bytes

# Color tags for the log widget
# Config file for persistent settings
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "bootloader_host")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")

# ── Dark Neon Dashboard Color Palette ────────────────────────────────
# Base
COLOR_BG         = "#0B1020"   # Deep navy-black (dashboard background)
COLOR_PANEL      = "#131C2E"   # Cool dark blue (glass card surface)
COLOR_PANEL_ALT  = "#1A2236"   # Slightly lighter for contrast
COLOR_TERMINAL   = "#0A0F1A"   # Very dark for log console

# Text
COLOR_FG         = "#E6E6E6"   # Primary text
COLOR_MUTED      = "#6B7280"   # Muted/secondary text

# Neon accents
COLOR_ACCENT     = "#22D3EE"   # Cyan neon (primary)
COLOR_ACCENT2    = "#D946EF"   # Magenta neon (secondary)
COLOR_SUCCESS    = "#22C55E"   # Green
COLOR_WARNING    = "#F59E0B"   # Amber
COLOR_ERROR      = "#EF4444"   # Red

# Borders
COLOR_BORDER     = "#1E2A45"   # Dark blue border

LOG_TAGS = {
    "info":    {"foreground": COLOR_FG,         "background": COLOR_TERMINAL},
    "success": {"foreground": COLOR_SUCCESS,     "background": COLOR_TERMINAL},
    "error":   {"foreground": COLOR_ERROR,       "background": COLOR_TERMINAL},
    "debug":   {"foreground": "#9CA3AF", "font": ("Consolas", 9, "italic"),
                                 "background": COLOR_TERMINAL},
    "warning": {"foreground": COLOR_WARNING,     "background": COLOR_TERMINAL},
    "data":    {"foreground": "#7DD3FC",  "font": ("Consolas", 9),
                                 "background": COLOR_TERMINAL},
}

# RDP level descriptions
RDP_LEVELS = {
    0: "Level 0 (no protection)",
    1: "Level 1 (read protection)",
    2: "Level 2 (no debug)",
}


# ---------------------------------------------------------------------------
# Dataclasses for command specification
# ---------------------------------------------------------------------------

@dataclass
class FieldSpec:
    """Specification for one parameter field in the dynamic form."""
    name: str
    label: str
    field_type: str = "text"   # "text", "int", "address", "hex", "file", "bool"
    default: str | int | bool = ""
    width: int = 28
    browse: bool = False       # show a Browse button (for file fields)


@dataclass
class CommandSpec:
    """Specification for one bootloader command."""
    key: str
    label: str
    hint: str = ""
    fields: list = field(default_factory=list)
    handler_name: str = ""


# ---------------------------------------------------------------------------
# Command definitions
# ---------------------------------------------------------------------------

COMMAND_DEFS: list[dict] = [
    {"key": "version",       "label": "Version",
     "hint": "Read bootloader version byte from the target."},
    {"key": "chip_id",       "label": "Chip ID",
     "hint": "Read the MCU chip identification (DBGMCU_IDCODE)."},
    {"key": "rdp_status",    "label": "RDP Status",
     "hint": "Read current readout protection level."},
    {"key": "help",          "label": "Help",
     "hint": "List supported bootloader commands."},
    {"key": "sector_status", "label": "Sector Status",
     "hint": "Read flash sector protection status."},
    {"key": "enable_protect", "label": "Enable R/W Protection",
     "hint": "Enable read/write protection on specified flash sectors.",
     "fields": [
         FieldSpec("sectors", "Sectors (comma-separated)", "text", "2,3,4", width=20),
     ]},
    {"key": "disable_protect", "label": "Disable R/W Protection",
     "hint": "Disable read/write protection on specified flash sectors.",
     "fields": [
         FieldSpec("sectors", "Sectors (comma-separated)", "text", "2,3,4", width=20),
     ]},
    {"key": "erase",         "label": "Erase Flash",
     "hint": "Erase one or more flash sectors, or use 0xFF for mass erase.",
     "fields": [
         FieldSpec("sector", "Start sector", "int", 2, width=8),
         FieldSpec("count",  "Sector count", "int", 1, width=8),
     ]},
    {"key": "read",          "label": "Read Memory",
     "hint": "Read bytes from flash or RAM at a specified address.",
     "fields": [
         FieldSpec("address", "Address", "address", DEFAULT_ADDRESS),
         FieldSpec("length",  "Length (bytes)", "int", 256),
     ]},
    {"key": "write",         "label": "Write Memory",
     "hint": "Write hex data or a binary file to memory.",
     "fields": [
         FieldSpec("address",  "Address",     "address", DEFAULT_ADDRESS),
         FieldSpec("data_hex", "Hex data",    "hex",     "", width=40),
         FieldSpec("file_path","Binary file", "file",    "", browse=True),
     ]},
    {"key": "send_fw",       "label": "Send Firmware",
     "hint": "Send a firmware binary with optional erase, verify, and auto-jump.",
     "fields": [
         FieldSpec("file_path",  "Firmware file", "file",    "", browse=True),
         FieldSpec("address",    "Start address", "address", DEFAULT_ADDRESS),
         FieldSpec("chunk_size", "Chunk size",    "int",     128, width=8),
         FieldSpec("erase",      "Erase first",   "bool",    False),
         FieldSpec("verify",     "Verify after",  "bool",    False),
         FieldSpec("go",         "Jump after",    "bool",    False),
     ]},
    {"key": "go_to",         "label": "Go To Address",
     "hint": "Jump execution to a specified address (launch application).",
     "fields": [
         FieldSpec("address", "Address", "address", DEFAULT_ADDRESS),
     ]},
    {"key": "otp_read",       "label": "OTP Read",
     "hint": "Read OTP (One-Time Programmable) memory contents.",
     "fields": [
         FieldSpec("address", "OTP Address", "address", "0x1FFF7800"),
         FieldSpec("length",  "Length (bytes)", "int", 32),
     ]},
    {"key": "raw",           "label": "Raw Command",
     "hint": "Send a raw bootloader command frame (advanced).",
     "fields": [
         FieldSpec("cmd",  "Command (hex)", "hex", "0x51", width=10),
         FieldSpec("data", "Data (hex)",    "hex", "",     width=40),
     ]},
]

COMMAND_SPECS: list[CommandSpec] = []
for d in COMMAND_DEFS:
    COMMAND_SPECS.append(CommandSpec(
        key=d["key"],
        label=d["label"],
        hint=d.get("hint", ""),
        fields=d.get("fields", []),
    ))

COMMAND_MAP = {spec.key: spec for spec in COMMAND_SPECS}

# Combobox display labels
COMMAND_LABELS = [spec.label for spec in COMMAND_SPECS]
COMMAND_LABEL_TO_KEY = {spec.label: spec.key for spec in COMMAND_SPECS}
COMMAND_KEY_TO_LABEL = {spec.key: spec.label for spec in COMMAND_SPECS}


# ---------------------------------------------------------------------------
# Main GUI class
# ---------------------------------------------------------------------------

class BootloaderGUI(tk.Tk):
    """Tkinter GUI application for the STM32F4 bootloader host."""

    # ── Lifecycle ──────────────────────────────────────────────────────

    def __init__(self) -> None:
        super().__init__()
        self.title("STM32F4 Bootloader Host")

        # Apply dark theme style
        self._apply_style()

        # Set default fonts for all widgets
        self.option_add("*Font", ("Segoe UI", 10))
        self.option_add("*TEntry*Font", ("Segoe UI", 10))
        self.option_add("*TCombobox*Font", ("Segoe UI", 10))

        # Configure background for the root window
        self.configure(bg=COLOR_BG)

        # Load saved settings
        self._settings = self._load_settings()

        # Restore previous window geometry or center
        prev_geo = self._settings.get("geometry", "")
        if prev_geo:
            self.geometry(prev_geo)
        else:
            self.update_idletasks()
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            x = (screen_w - 860) // 2
            y = (screen_h - 680) // 2
            self.geometry(f"860x680+{x}+{y}")
        self.minsize(700, 500)

        # Remember saved baud for after UI is built
        self._saved_baud = self._settings.get("last_baud", str(DEFAULT_BAUD))
        if self._saved_baud not in [str(b) for b in BAUD_OPTIONS]:
            self._saved_baud = str(DEFAULT_BAUD)

        # Keyboard shortcuts
        self.bind("<Return>", lambda e: self._on_execute())
        self.bind("<Control-l>", lambda e: self._clear_log())
        self.bind("<Control-q>", lambda e: self._on_close())
        self.bind("<F5>", lambda e: self._refresh_ports())
        self.bind("<Control-r>", lambda e: self._refresh_ports())

        # ── State ──
        self.client: Optional[BootloaderClient] = None
        self.connected: bool = False
        self.busy: bool = False
        self.current_command: str = "version"
        self.worker_thread: Optional[threading.Thread] = None
        self.ui_queue: queue.Queue = queue.Queue()
        self.field_vars: dict[str, tk.Variable] = {}
        self.param_widgets: list[tk.Widget] = []
        self.cancel_event = threading.Event()

        # ── Build UI ──
        self._build_ui()

        # ── Restore saved baud rate ──
        self.baud_var.set(self._saved_baud)

        # ── Initial state ──
        self._refresh_ports()
        self._select_command("version")
        self._apply_ui_state()

        # ── Queue polling ──
        self.after(50, self._poll_queue)

        # Handle close
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI Construction ────────────────────────────────────────────────

    # -------------------------------------------------------------------
    # Neon / Glass panel helpers
    # -------------------------------------------------------------------

    def _create_neon_panel(self, parent: tk.Widget,
                            title: str = "",
                            side: str = tk.TOP,
                            fill: str = tk.X,
                            expand: bool = False,
                            padx: int = 6,
                            pady_top: int = 4,
                            pady_bot: int = 0,
                            ) -> tuple[tk.Frame, tk.Frame, tk.Frame]:
        """
        Build a glass-inspired neon card panel.

        Returns (glow_frame, border_frame, inner_frame).
        Pack content widgets into *inner_frame*.
        """
        # Glow border (bright accent, 1px)
        glow = tk.Frame(parent, bg=COLOR_ACCENT, highlightthickness=0)
        glow.pack(fill=fill, side=side, expand=expand,
                  padx=padx, pady=(pady_top, pady_bot))

        # Border layer (darker blue)
        border = tk.Frame(glow, bg=COLOR_BORDER, highlightthickness=0,
                          padx=1, pady=1)
        border.pack(fill=fill, expand=expand)

        # Inner panel (dark blue surface)
        inner = tk.Frame(border, bg=COLOR_PANEL, highlightthickness=0,
                         padx=1, pady=1)
        inner.pack(fill=fill, expand=expand)

        if title:
            self._create_section_header(inner, title,
                                        padx=8, pady=(6, 0))

        return glow, border, inner

    def _create_section_header(self, inner: tk.Frame, title: str,
                                padx: int = 8, pady: tuple = (6, 0)) -> None:
        """
        Place an uppercase section title with a neon underline inside *inner*.
        """
        hdr = tk.Frame(inner, bg=COLOR_PANEL)
        hdr.pack(fill=tk.X, padx=padx, pady=pady)

        tk.Label(
            hdr, text=title.upper(),
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_ACCENT, bg=COLOR_PANEL,
            anchor=tk.W,
        ).pack(side=tk.LEFT)

        # Thin accent underline
        line = tk.Frame(hdr, height=1, bg=COLOR_ACCENT)
        line.pack(fill=tk.X, side=tk.BOTTOM, pady=(2, 4))

    def _apply_style(self) -> None:
        """Apply a dark neon dashboard theme using ttk.Style."""
        style = ttk.Style()
        style.theme_use("clam")

        # ── Global defaults ──
        style.configure(".",
            background=COLOR_BG,
            foreground=COLOR_FG,
            fieldbackground=COLOR_PANEL,
            bordercolor=COLOR_BORDER,
            lightcolor=COLOR_PANEL,
            darkcolor=COLOR_BORDER,
        )

        # ── Frames ──
        style.configure("TFrame", background=COLOR_BG)
        style.configure("NeonPanel.TFrame", background=COLOR_PANEL)
        style.configure("TLabelframe", background=COLOR_BG, foreground=COLOR_FG,
                         bordercolor=COLOR_BORDER, lightcolor=COLOR_BORDER)
        style.configure("TLabelframe.Label", background=COLOR_BG, foreground=COLOR_FG)

        # ── Labels ──
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_FG)
        style.configure("NeonPanel.TLabel", background=COLOR_PANEL, foreground=COLOR_FG)
        style.configure("Heading.TLabel",
            background=COLOR_BG, foreground=COLOR_FG,
            font=("Segoe UI", 10, "bold"))
        style.configure("Hint.TLabel",
            background=COLOR_BG, foreground=COLOR_MUTED,
            font=("Segoe UI", 9))
        style.configure("Section.TLabel",
            background=COLOR_PANEL, foreground=COLOR_ACCENT,
            font=("Segoe UI", 8, "bold"))

        # ── Buttons ──
        style.configure("TButton",
            background=COLOR_PANEL_ALT, foreground=COLOR_FG,
            bordercolor=COLOR_BORDER, focuscolor="none",
            lightcolor=COLOR_PANEL_ALT, darkcolor=COLOR_BORDER,
        )
        style.map("TButton",
            background=[("active", "#1E3350"), ("pressed", "#253F60"),
                        ("disabled", COLOR_BG)],
            foreground=[("disabled", COLOR_MUTED)],
        )

        # ── Accent (Execute) button — cyan neon ──
        style.configure("Accent.TButton",
            background=COLOR_ACCENT, foreground="#0B1020",
            bordercolor=COLOR_ACCENT, focuscolor="none",
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Accent.TButton",
            background=[("active", "#67E8F9"), ("pressed", "#06B6D4"),
                        ("disabled", COLOR_BG)],
            foreground=[("disabled", COLOR_MUTED)],
        )

        # ── Danger (Cancel) button — amber ──
        style.configure("Danger.TButton",
            background=COLOR_WARNING, foreground="#0B1020",
            bordercolor=COLOR_WARNING, focuscolor="none",
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Danger.TButton",
            background=[("active", "#FBBF24"), ("pressed", "#D97706"),
                        ("disabled", COLOR_BG)],
            foreground=[("disabled", COLOR_MUTED)],
        )

        # ── Combobox ──
        style.configure("TCombobox",
            fieldbackground=COLOR_PANEL_ALT, foreground=COLOR_FG,
            background=COLOR_PANEL_ALT, bordercolor=COLOR_BORDER,
            arrowcolor=COLOR_ACCENT, selectbackground=COLOR_ACCENT,
            selectforeground="#0B1020",
        )
        style.map("TCombobox",
            fieldbackground=[("disabled", COLOR_BG)],
            foreground=[("disabled", COLOR_MUTED)],
            background=[("disabled", COLOR_BG)],
        )

        # ── Entry ──
        style.configure("TEntry",
            fieldbackground=COLOR_PANEL_ALT, foreground=COLOR_FG,
            bordercolor=COLOR_BORDER, selectbackground=COLOR_ACCENT,
            selectforeground="#0B1020",
        )
        style.map("TEntry",
            fieldbackground=[("disabled", COLOR_BG)],
            foreground=[("disabled", COLOR_MUTED)],
        )

        # ── Checkbutton ──
        style.configure("TCheckbutton",
            background=COLOR_BG, foreground=COLOR_FG,
            focuscolor="none",
        )
        style.map("TCheckbutton",
            background=[("active", COLOR_PANEL)],
            foreground=[("disabled", COLOR_MUTED)],
        )

        # ── Progressbar — cyan neon trough ──
        style.configure("Horizontal.TProgressbar",
            background=COLOR_ACCENT, troughcolor=COLOR_PANEL_ALT,
            bordercolor=COLOR_BORDER, lightcolor=COLOR_ACCENT,
        )

        # ── Status bar ──
        style.configure("StatusBar.TFrame", background=COLOR_PANEL_ALT)
        style.configure("StatusBar.TLabel",
            background=COLOR_PANEL_ALT, foreground=COLOR_MUTED,
            font=("Segoe UI", 9),
        )

        # ── Terminal log ──
        style.configure("Log.TFrame", background=COLOR_TERMINAL)
        style.configure("LogHeader.TFrame", background=COLOR_PANEL)

    def _build_ui(self) -> None:
        """Build all UI panels."""
        self._build_connection_panel()
        self._build_command_selector()
        self._build_parameter_panel()
        self._build_progress_panel()
        self._build_log_panel()
        self._build_status_bar()

    def _build_connection_panel(self) -> None:
        """Top row: COM port, baud, refresh, connect, status — in a neon card."""
        _, _, inner = self._create_neon_panel(self, title="Connection",
                                               pady_top=6, pady_bot=0)

        # Content row
        row = tk.Frame(inner, bg=COLOR_PANEL)
        row.pack(fill=tk.X, padx=8, pady=(0, 6))

        # COM port
        tk.Label(row, text="Port:", font=("Segoe UI", 10, "bold"),
                 fg=COLOR_ACCENT, bg=COLOR_PANEL
                 ).pack(side=tk.LEFT, padx=(0, 4))
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(
            row, textvariable=self.port_var, width=18, state="readonly"
        )
        self.port_combo.pack(side=tk.LEFT, padx=(0, 4))

        # Refresh button
        self.refresh_btn = ttk.Button(
            row, text="⟳", width=3, command=self._refresh_ports
        )
        self.refresh_btn.pack(side=tk.LEFT, padx=(0, 12))

        # Baud rate
        tk.Label(row, text="Baud:", font=("Segoe UI", 10, "bold"),
                 fg=COLOR_ACCENT, bg=COLOR_PANEL
                 ).pack(side=tk.LEFT, padx=(0, 4))
        self.baud_var = tk.StringVar(value=str(DEFAULT_BAUD))
        self.baud_combo = ttk.Combobox(
            row, textvariable=self.baud_var,
            values=[str(b) for b in BAUD_OPTIONS],
            width=8, state="readonly",
        )
        self.baud_combo.pack(side=tk.LEFT, padx=(0, 12))

        # Connect / Disconnect button
        self.connect_btn = ttk.Button(
            row, text="Connect", width=12, command=self._on_connect_clicked
        )
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 12))

        # Status indicator
        self.status_canvas = tk.Canvas(row, width=12, height=12,
                                        highlightthickness=0, bd=0,
                                        bg=COLOR_PANEL)
        self.status_canvas.pack(side=tk.LEFT, padx=(0, 4))
        self._draw_status_dot("red")

        self.status_label = tk.Label(row, text="Disconnected",
                                      font=("Segoe UI", 9),
                                      fg=COLOR_MUTED, bg=COLOR_PANEL)
        self.status_label.pack(side=tk.LEFT)

    def _draw_status_dot(self, color: str) -> None:
        """Draw a colored circle on the status canvas."""
        self.status_canvas.delete("all")
        r = 5
        self.status_canvas.create_oval(
            6 - r, 6 - r, 6 + r, 6 + r, fill=color, outline=color
        )

    def _build_command_selector(self) -> None:
        """Command dropdown selector with description hint — in a neon card."""
        _, _, inner = self._create_neon_panel(self, title="Command",
                                               pady_top=4, pady_bot=0)

        row = tk.Frame(inner, bg=COLOR_PANEL)
        row.pack(fill=tk.X, padx=8, pady=(0, 6))

        tk.Label(row, text="Command:", font=("Segoe UI", 10, "bold"),
                 fg=COLOR_ACCENT2, bg=COLOR_PANEL
                 ).pack(side=tk.LEFT, padx=(0, 8))

        self.command_var = tk.StringVar()
        self.command_combo = ttk.Combobox(
            row, textvariable=self.command_var,
            values=COMMAND_LABELS, width=24, state="readonly",
            font=("Segoe UI", 10),
        )
        self.command_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.command_combo.bind("<<ComboboxSelected>>", self._on_command_selected)

        # Hint/description label
        self.command_hint_var = tk.StringVar()
        self.command_hint_label = tk.Label(
            row, textvariable=self.command_hint_var,
            font=("Segoe UI", 9, "italic"),
            fg=COLOR_MUTED, bg=COLOR_PANEL,
        )
        self.command_hint_label.pack(side=tk.LEFT, padx=(8, 0))

    def _build_parameter_panel(self) -> None:
        """
        Parameter panel with two persistent sub-frames — in a neon card.
          - param_fields_frame: rebuilt when command changes
          - param_actions_frame: permanent Execute + Cancel buttons
        """
        _, _, inner = self._create_neon_panel(self, title="Parameters",
                                               pady_top=4, pady_bot=0)

        # Field area — gets rebuilt
        self.param_fields_frame = tk.Frame(inner, bg=COLOR_PANEL)
        self.param_fields_frame.pack(fill=tk.X, expand=True, padx=6, pady=(0, 0))

        # Action buttons — persistent, never destroyed
        self.param_actions_frame = tk.Frame(inner, bg=COLOR_PANEL)
        self.param_actions_frame.pack(fill=tk.X, padx=6, pady=(6, 6))

        # Cancel button (left of execute) — Danger style
        self.cancel_btn = ttk.Button(
            self.param_actions_frame, text="■ Cancel", width=14,
            command=self._on_cancel, style="Danger.TButton",
        )
        self.cancel_btn.pack(side=tk.RIGHT, padx=(0, 6))

        # Execute button — Accent style
        self.execute_btn = ttk.Button(
            self.param_actions_frame, text="▶ Execute", width=20,
            command=self._on_execute, style="Accent.TButton",
        )
        self.execute_btn.pack(side=tk.RIGHT)

    def _build_progress_panel(self) -> None:
        """Progress bar area in a neon panel (initially hidden)."""
        _glow, _border, inner = self._create_neon_panel(
            self, title="Progress", pady_top=4, pady_bot=0
        )
        self.progress_glow = _glow
        self.progress_frame = inner
        self._show_progress(False)

        row = tk.Frame(inner, bg=COLOR_PANEL)
        row.pack(fill=tk.X, padx=8, pady=(0, 6))

        self.progress_bar = ttk.Progressbar(
            row, mode="determinate", length=400
        )
        self.progress_bar.pack(side=tk.LEFT, padx=(0, 8))

        self.progress_label = tk.Label(row, text="",
                                        font=("Segoe UI", 9),
                                        fg=COLOR_MUTED, bg=COLOR_PANEL)
        self.progress_label.pack(side=tk.LEFT)

    # ── Log Panel (Terminal Console) ──────────────────────────────────────

    def _build_log_panel(self) -> None:
        """
        Terminal-style log output area in a neon-bordered console panel.
        """
        # Glow border frame (cyan neon border around the log)
        self._log_glow = glow = tk.Frame(self, bg=COLOR_ACCENT, highlightthickness=0)
        glow.pack(fill=tk.BOTH, expand=True, side=tk.BOTTOM,
                  padx=6, pady=(2, 6))

        # Border layer
        border = tk.Frame(glow, bg=COLOR_BORDER, highlightthickness=0,
                          padx=1, pady=1)
        border.pack(fill=tk.BOTH, expand=True)

        # Terminal-style inner panel (very dark)
        inner = tk.Frame(border, bg=COLOR_TERMINAL, highlightthickness=0,
                         padx=1, pady=1)
        inner.pack(fill=tk.BOTH, expand=True)

        # ── Header ──
        hdr = tk.Frame(inner, bg=COLOR_PANEL, highlightthickness=0)
        hdr.pack(fill=tk.X)

        # Cyan "$" prompt-like indicator + OUTPUT label
        tk.Label(
            hdr,
            text="$ ",
            font=("Consolas", 10, "bold"),
            fg=COLOR_SUCCESS, bg=COLOR_PANEL,
        ).pack(side=tk.LEFT, padx=(8, 2), pady=4)

        tk.Label(
            hdr,
            text="OUTPUT",
            font=("Segoe UI", 8, "bold"),
            fg=COLOR_ACCENT, bg=COLOR_PANEL,
        ).pack(side=tk.LEFT, pady=4)

        # Clear button
        clear_btn = ttk.Button(
            hdr, text="🗑 Clear", width=8,
            command=self._clear_log,
        )
        clear_btn.pack(side=tk.RIGHT, padx=(4, 8), pady=2)

        # About button
        about_btn = ttk.Button(
            hdr, text="ℹ About", width=8,
            command=self._show_about,
        )
        about_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=2)

        # Thin accent line under header
        line = tk.Frame(inner, height=1, bg=COLOR_ACCENT)
        line.pack(fill=tk.X)

        # ── Log text widget ──
        self.log_text = scrolledtext.ScrolledText(
            inner, wrap=tk.WORD, font=("Consolas", 10),
            state=tk.DISABLED, height=12,
            bg=COLOR_TERMINAL, fg=COLOR_FG,
            insertbackground=COLOR_ACCENT,  # cyan cursor
            relief=tk.FLAT, bd=0,
            highlightthickness=0,
            padx=8, pady=6,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configure tags
        for tag, attrs in LOG_TAGS.items():
            self.log_text.tag_configure(tag, **attrs)

    # ── Status Bar (Instrument Strip) ──────────────────────────────────

    def _build_status_bar(self) -> None:
        """
        Bottom instrument-strip status bar with neon accent top border.
        """
        # Accent top line (pack before the log panel glow frame)
        accent_line = tk.Frame(self, height=2, bg=COLOR_ACCENT)
        accent_line.pack(fill=tk.X, side=tk.BOTTOM, before=self._log_glow)

        self.status_bar = tk.Frame(self, bg=COLOR_PANEL_ALT, height=26)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, before=accent_line, pady=0)

        # Left: connection + current command icon
        status_icon = tk.Label(
            self.status_bar, text="⏻",
            font=("Segoe UI", 10),
            fg=COLOR_MUTED, bg=COLOR_PANEL_ALT,
        )
        status_icon.pack(side=tk.LEFT, padx=(10, 4))

        self.status_bar_label = tk.Label(
            self.status_bar,
            text="READY — connect to a device",
            font=("Consolas", 9),
            fg=COLOR_MUTED, bg=COLOR_PANEL_ALT,
        )
        self.status_bar_label.pack(side=tk.LEFT)

        # Separator line
        sep = tk.Frame(self.status_bar, width=1, bg=COLOR_BORDER)
        sep.pack(side=tk.LEFT, padx=(12, 8), fill=tk.Y)

        # Right side: keyboard shortcut hints
        hints_frame = tk.Frame(self.status_bar, bg=COLOR_PANEL_ALT)
        hints_frame.pack(side=tk.RIGHT, padx=(0, 10))

        hints = [
            ("Enter", "Execute"),
            ("Ctrl+L", "Clear"),
            ("F5", "Refresh"),
            ("Ctrl+Q", "Quit"),
        ]
        for key, action in hints:
            kbd = tk.Label(
                hints_frame,
                text=key,
                font=("Consolas", 8, "bold"),
                fg=COLOR_ACCENT, bg=COLOR_PANEL_ALT,
            )
            kbd.pack(side=tk.LEFT, padx=(6, 0))
            act = tk.Label(
                hints_frame,
                text=action,
                font=("Segoe UI", 8),
                fg=COLOR_MUTED, bg=COLOR_PANEL_ALT,
            )
            act.pack(side=tk.LEFT, padx=(2, 0))

    # ── About Dialog ──────────────────────────────────────────────────

    def _show_about(self) -> None:
        """Show the About dialog with neon theme styling."""
        about = tk.Toplevel(self)
        about.title("About STM32F4 Bootloader Host")
        about.configure(bg=COLOR_BG)
        about.resizable(False, False)

        # Center on parent
        x = self.winfo_x() + (self.winfo_width() - 380) // 2
        y = self.winfo_y() + (self.winfo_height() - 280) // 2
        about.geometry(f"380x280+{x}+{y}")

        # Neon border wrapper
        glow = tk.Frame(about, bg=COLOR_ACCENT, padx=1, pady=1)
        glow.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        border = tk.Frame(glow, bg=COLOR_BORDER, padx=1, pady=1)
        border.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(border, bg=COLOR_PANEL)
        inner.pack(fill=tk.BOTH, expand=True)

        # ── Header ──
        hdr = tk.Frame(inner, bg=COLOR_PANEL)
        hdr.pack(fill=tk.X, padx=20, pady=(20, 0))

        tk.Label(
            hdr, text="STM32F4 Bootloader Host",
            font=("Segoe UI", 14, "bold"),
            fg=COLOR_ACCENT, bg=COLOR_PANEL,
        ).pack(anchor=tk.CENTER)

        tk.Label(
            hdr, text="Version 1.0.0",
            font=("Segoe UI", 10),
            fg=COLOR_ACCENT2, bg=COLOR_PANEL,
        ).pack(anchor=tk.CENTER, pady=(4, 0))

        # Neon divider
        div = tk.Frame(inner, height=1, bg=COLOR_ACCENT)
        div.pack(fill=tk.X, padx=80, pady=(12, 0))

        # ── Body ──
        body = tk.Frame(inner, bg=COLOR_PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=20, pady=(12, 8))

        tk.Label(
            body,
            text="A graphical host tool for the\nSTM32F4 Custom Bootloader.",
            font=("Segoe UI", 10),
            fg=COLOR_FG, bg=COLOR_PANEL,
            justify=tk.CENTER,
        ).pack(anchor=tk.CENTER)

        tk.Label(
            body,
            text="",
            bg=COLOR_PANEL,
        ).pack(pady=(8, 0))

        tk.Label(
            body,
            text="Firmware upload  ·  Flash erase  ·  Memory R/W\n"
                 "Sector management  ·  Raw commands",
            font=("Segoe UI", 9),
            fg=COLOR_MUTED, bg=COLOR_PANEL,
            justify=tk.CENTER,
        ).pack(anchor=tk.CENTER)

        # ── Close button ──
        close_frame = tk.Frame(inner, bg=COLOR_PANEL)
        close_frame.pack(fill=tk.X, pady=(0, 16))

        ttk.Button(
            close_frame, text="Close", width=12,
            command=about.destroy,
        ).pack(anchor=tk.CENTER)

        # Make modal-ish
        about.transient(self)
        about.grab_set()
        about.focus_set()

    # ── Settings Persistence ───────────────────────────────────────────

    def _load_settings(self) -> dict:
        """Load saved settings from disk."""
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save_settings(self) -> None:
        """Save current settings to disk."""
        settings = {
            "last_port": self.port_var.get(),
            "last_baud": self.baud_var.get(),
            "geometry": self.geometry(),
        }
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                json.dump(settings, f, indent=2)
        except OSError:
            pass  # Silently ignore save failures

    # ── Central UI State Manager ───────────────────────────────────────

    def _apply_ui_state(self) -> None:
        """
        Central method that updates ALL widget states from self.connected
        and self.busy. No other method should randomly toggle widget states.
        """
        connected = self.connected
        busy = self.busy

        # Connection controls
        self.refresh_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.port_combo.configure(state="disabled" if busy else "readonly")
        self.baud_combo.configure(state="disabled" if busy else "readonly")

        # Connect / Disconnect button
        connect_text = "Disconnect" if connected else "Connect"
        self.connect_btn.configure(
            text=connect_text,
            state=tk.DISABLED if busy else tk.NORMAL,
        )

        # Command selector
        self.command_combo.configure(
            state="disabled" if busy or not connected else "readonly"
        )

        # Parameter fields
        param_enabled = connected and not busy
        self._set_param_widgets_state(
            tk.DISABLED if not param_enabled else tk.NORMAL
        )

        # Action buttons
        self.execute_btn.configure(
            state=tk.NORMAL if connected and not busy else tk.DISABLED
        )
        self.cancel_btn.configure(
            state=tk.NORMAL if busy else tk.DISABLED
        )

        # Status dot and label
        if busy:
            self._draw_status_dot(COLOR_WARNING)
            self.status_label.configure(text="Busy...")
            self.status_bar_label.configure(text="Operation in progress...")
        elif connected:
            self._draw_status_dot(COLOR_SUCCESS)
            self.status_label.configure(text="Connected")
            # Build status bar text with port info
            port_info = ""
            if self.client:
                try:
                    if self.client.is_open:
                        port_info = f" @ {self.client.port}:{self.client.baudrate}"
                except Exception:
                    pass
            self.status_bar_label.configure(text=f"Connected{port_info}")
        else:
            self._draw_status_dot(COLOR_ERROR)
            self.status_label.configure(text="Disconnected")
            self.status_bar_label.configure(text="Ready — connect to a device")

    def _set_param_widgets_state(self, state: str) -> None:
        """Enable or disable all parameter field widgets."""
        for w in self.param_widgets:
            try:
                if isinstance(w, ttk.Combobox):
                    w.configure(
                        state="readonly" if state == tk.NORMAL else "disabled"
                    )
                elif isinstance(w, ttk.Checkbutton):
                    w.configure(state=state)
                elif isinstance(w, ttk.Entry):
                    w.configure(state=state)
                elif isinstance(w, ttk.Button):
                    w.configure(state=state)
                else:
                    w.configure(state=state)
            except (tk.TclError, Exception):
                pass

    # ── Connection Management ─────────────────────────────────────────

    def _refresh_ports(self) -> None:
        """Refresh the list of available serial ports."""
        try:
            ports = list_available_ports()
        except Exception as e:
            self._log(f"Failed to list ports: {e}", "error")
            return

        devices = [p["device"] for p in ports]
        current = self.port_var.get()

        self.port_combo["values"] = devices

        # Try to restore saved port, then current selection, then first available
        saved_port = self._settings.get("last_port", "")
        if saved_port in devices:
            self.port_var.set(saved_port)
        elif current in devices:
            self.port_var.set(current)
        elif devices:
            self.port_var.set(devices[0])
        else:
            self.port_var.set("")

        self._log(f"Found {len(devices)} serial port(s)", "debug")

    def _on_connect_clicked(self) -> None:
        """Connect to or disconnect from the bootloader."""
        if self.connected:
            self._disconnect()
        else:
            port = self.port_var.get()
            if not port:
                self._log("No COM port selected", "error")
                return
            self._start_worker(
                self._connect_worker,
                port,
                int(self.baud_var.get()),
                DEFAULT_TIMEOUT,
            )

    def _connect_worker(self, port: str, baud: int, timeout: float) -> None:
        """Background: open connection to the bootloader."""
        try:
            client = BootloaderClient(
                port, baud, timeout,
                trace_callback=self._trace_client_frame,
            )
            client.open()
            self.ui_queue.put({
                "type": "connected", "client": client,
                "port": port, "baud": baud,
            })
        except BootloaderError as e:
            self.ui_queue.put({
                "type": "log", "level": "error",
                "text": f"Connection failed: {e}",
            })
        except Exception as e:
            self.ui_queue.put({
                "type": "log", "level": "error",
                "text": f"Unexpected error: {e}",
            })
        finally:
            self.ui_queue.put({"type": "done"})

    def _disconnect(self) -> None:
        """Disconnect from the bootloader."""
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
        self.connected = False
        self._apply_ui_state()
        self._log("Disconnected", "info")

    # ── Command Selection ──────────────────────────────────────────────

    def _on_command_selected(self, event: Any = None) -> None:
        """Called when the user selects a command from the combobox."""
        label = self.command_var.get()
        key = COMMAND_LABEL_TO_KEY.get(label)
        if key:
            self._select_command(key)

    def _select_command(self, command_key: str) -> None:
        """Switch to a different command and rebuild the parameter form."""
        self.current_command = command_key
        spec = COMMAND_MAP[command_key]

        # Sync combobox
        self.command_var.set(spec.label)

        # Update hint text
        self.command_hint_var.set(spec.hint)

        # Rebuild parameter fields (NOT the action buttons)
        self._render_parameter_form(spec)

    def _render_parameter_form(self, spec: CommandSpec) -> None:
        """Rebuild only the parameter fields area — action buttons are persistent."""
        # Destroy old field widgets
        for w in self.param_fields_frame.winfo_children():
            w.destroy()
        self.field_vars.clear()
        self.param_widgets.clear()

        if not spec.fields:
            # No parameters needed — show label (not in param_widgets,
            # since Labels have no state attribute)
            lbl = tk.Label(
                self.param_fields_frame,
                text="This command does not require any parameters.\n"
                     "Click Execute to run it.",
                fg="#888", bg=COLOR_PANEL,
                justify=tk.LEFT,
            )
            lbl.pack(anchor=tk.W, pady=4)
        else:
            # Build form fields
            for i, field in enumerate(spec.fields):
                self._create_field_widget(self.param_fields_frame, field, i)

        # Update execute button text to reflect current command
        self.execute_btn.configure(text=f"▶ Execute {spec.label}")

        # Re-apply UI state so new widgets inherit correct enabled/disabled
        self._apply_ui_state()

    def _create_field_widget(self, parent: tk.Frame, field: FieldSpec,
                              row: int) -> None:
        """Create one parameter field row and track its widgets."""
        frame = tk.Frame(parent, bg=COLOR_PANEL)
        frame.pack(fill=tk.X, pady=2)

        # Label
        tk.Label(frame, text=field.label + ":", width=20,
                 anchor=tk.W, fg=COLOR_ACCENT, bg=COLOR_PANEL,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)

        if field.field_type == "bool":
            var = tk.BooleanVar(value=bool(field.default))
            cb = ttk.Checkbutton(frame, variable=var)
            cb.pack(side=tk.LEFT)
            self.field_vars[field.name] = var
            self.param_widgets.append(cb)

        elif field.field_type == "file":
            var = tk.StringVar(value=str(field.default) if field.default else "")
            entry = ttk.Entry(frame, textvariable=var, width=field.width)
            entry.pack(side=tk.LEFT, padx=(0, 4), fill=tk.X, expand=True)
            self.field_vars[field.name] = var
            self.param_widgets.append(entry)
            if field.browse:
                btn = ttk.Button(
                    frame, text="Browse...", width=10,
                    command=lambda n=field.name: self._browse_file(n),
                )
                btn.pack(side=tk.LEFT)
                self.param_widgets.append(btn)

        else:
            var = tk.StringVar(value=str(field.default) if field.default else "")
            entry = ttk.Entry(frame, textvariable=var, width=field.width)
            entry.pack(side=tk.LEFT, padx=(0, 4), fill=tk.X, expand=True)
            self.field_vars[field.name] = var
            self.param_widgets.append(entry)

    # ── Execute / Cancel ───────────────────────────────────────────────

    def _browse_file(self, field_name: str) -> None:
        """Open a file dialog and set the field variable."""
        filename = filedialog.askopenfilename(
            title="Select firmware binary",
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")],
        )
        if filename and field_name in self.field_vars:
            self.field_vars[field_name].set(filename)

    def _on_execute(self) -> None:
        """Execute the currently selected command."""
        if not self.connected:
            self._log("Not connected — connect first", "error")
            return
        if self.busy:
            self._log("Already busy — wait for current operation", "warning")
            return

        spec = COMMAND_MAP[self.current_command]
        try:
            params = self._collect_params(spec)
        except ValidationError as e:
            self._log(f"Parameter error: {e}", "error")
            return

        # Prepare for execution
        self.cancel_event.clear()
        self._log(f"▶ Executing {spec.label}...", "info")
        self._start_worker(self._command_worker, self.current_command, params)

    def _on_cancel(self) -> None:
        """Request cancellation of the current operation."""
        if not self.busy:
            return
        self.cancel_event.set()
        self._log("■ Cancellation requested — finishing current chunk...", "warning")

        # For blocking serial reads, force-close the port to unblock the worker
        # Need to force close from main thread to break blocking read
        # We do this in a timer to give the worker a moment to check
        if self.client and self.client.is_open:
            self.after(100, self._force_cancel)

    def _force_cancel(self) -> None:
        """Forcefully close the serial port to unblock a stuck worker."""
        if not self.busy:
            return
        if self.client and self.client.is_open:
            try:
                self._log("Forcing serial disconnect to abort operation...", "debug")
                self.client.close()
            except Exception:
                pass

    # ── Parameter Collection ───────────────────────────────────────────

    def _collect_params(self, spec: CommandSpec) -> dict:
        """Collect parameter values from the form into a dict."""
        params = {}
        for field in spec.fields:
            var = self.field_vars.get(field.name)
            if var is None:
                continue
            raw = var.get()

            if field.field_type == "bool":
                params[field.name] = bool(raw)
            elif field.field_type == "int":
                try:
                    # int(raw, 0) auto-detects base: 10 → 10, 0xFF → 255, 0x10 → 16
                    params[field.name] = int(raw, 0) if raw.strip() else 0
                except (ValueError, TypeError):
                    raise ValidationError(
                        f"{field.label}: expected integer or hex (e.g. 0xFF), got '{raw}'"
                    )
            elif field.field_type == "address":
                params[field.name] = self._parse_address(raw)
            elif field.field_type == "hex":
                params[field.name] = raw.strip()
            elif field.field_type == "file":
                params[field.name] = raw.strip()
            else:
                params[field.name] = raw.strip()
        return params

    # ── Worker Thread Management ───────────────────────────────────────

    def _start_worker(self, target: Callable, *args: Any, **kwargs: Any) -> None:
        """Start a background worker thread and update UI state."""
        self.busy = True
        self._apply_ui_state()
        self.worker_thread = threading.Thread(
            target=target, args=args, kwargs=kwargs,
            daemon=True,
        )
        self.worker_thread.start()

    def _command_worker(self, command_key: str, params: dict) -> None:
        """Background: dispatch command execution to the handler."""
        handlers = {
            "version":       self._exec_version,
            "chip_id":       self._exec_chip_id,
            "rdp_status":    self._exec_rdp_status,
            "help":          self._exec_help,
            "sector_status": self._exec_sector_status,
            "enable_protect": self._exec_enable_protect,
            "disable_protect": self._exec_disable_protect,
            "erase":         self._exec_erase,
            "read":          self._exec_read,
            "write":         self._exec_write,
            "send_fw":       self._exec_send_firmware,
            "go_to":         self._exec_go_to,
            "otp_read":      self._exec_otp_read,
            "raw":           self._exec_raw,
        }
        handler = handlers.get(command_key)
        if handler is None:
            self.ui_queue.put({
                "type": "log", "level": "error",
                "text": f"Unknown command: {command_key}",
            })
            self.ui_queue.put({"type": "done"})
            return

        try:
            handler(params)
        except _OperationCancelled:
            self.ui_queue.put({
                "type": "log", "level": "warning",
                "text": "Operation cancelled by user",
            })
        except NackError as e:
            self.ui_queue.put({
                "type": "log", "level": "error",
                "text": f"NACK: {e}",
            })
        except TimeoutError as e:
            self.ui_queue.put({
                "type": "log", "level": "error",
                "text": f"Timeout: {e}",
            })
        except ValidationError as e:
            self.ui_queue.put({
                "type": "log", "level": "error",
                "text": f"Parameter error: {e}",
            })
        except BootloaderError as e:
            self.ui_queue.put({
                "type": "log", "level": "error",
                "text": f"Bootloader error: {e}",
            })
        except Exception as e:
            self.ui_queue.put({
                "type": "log", "level": "error",
                "text": f"Error: {e}",
            })
        finally:
            self.ui_queue.put({"type": "progress_hide"})
            self.ui_queue.put({"type": "done"})

    # ── Command Handlers (run in worker thread) ────────────────────────

    def _exec_version(self, params: dict) -> None:
        """Handle Version command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        ver = self.client.get_version()
        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": f"Bootloader version: 0x{ver:02X} ({ver})",
        })

    def _exec_chip_id(self, params: dict) -> None:
        """Handle Chip ID command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        cid = self.client.get_chip_id()
        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": f"Chip ID: 0x{cid:04X}",
        })

    def _exec_rdp_status(self, params: dict) -> None:
        """Handle RDP Status command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        status = self.client.get_rdp_status()
        desc = RDP_LEVELS.get(status, f"Unknown (0x{status:02X})")
        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": f"RDP Status: 0x{status:02X} ({desc})",
        })

    def _exec_help(self, params: dict) -> None:
        """Handle Help command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        try:
            data = self.client.get_help()
        except Exception:
            data = b""
        if data:
            lines = ["Supported commands (from device):"]
            for b in data:
                name = COMMAND_NAMES.get(b, "UNKNOWN")
                lines.append(f"  0x{b:02X}  {name}")
        else:
            lines = ["Known command codes (device did not respond):"]
            for code, name in sorted(COMMAND_NAMES.items()):
                lines.append(f"  0x{code:02X}  {name}")
        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": "\n".join(lines),
        })

    def _exec_sector_status(self, params: dict) -> None:
        """Handle Sector Status command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        data = self.client.read_sector_status()
        if not data:
            self.ui_queue.put({
                "type": "log", "level": "warning",
                "text": "No sector status data returned",
            })
            return
        lines = ["Sector protection status:"]
        if len(data) >= 2:
            # C firmware sends 12-bit WRP bitmask packed into 2 bytes
            # (active-low: 0 = protected, 1 = not protected)
            wrp_status = data[0] | ((data[1] & 0x0F) << 8)
            for i in range(12):
                is_protected = not (wrp_status & (1 << i))
                status_char = chr(0x1f512) if is_protected else chr(0x1f513)
                status_label = "Protected" if is_protected else "Unprotected"
                lines.append(f"  Sector {i:2d}: {status_char} {status_label}")
        else:
            for i, b in enumerate(data[:12]):
                status_char = chr(0x1f512) if b else chr(0x1f513)
                status_label = "Protected" if b else "Unprotected"
                lines.append(f"  Sector {i:2d}: {status_char} {status_label}")
            status = "🔒 Protected" if b else "🔓 Unprotected"
            lines.append(f"  Sector {i:2d}: {status}")
        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": "\n".join(lines),
        })

    def _exec_enable_protect(self, params: dict) -> None:
        """Handle Enable R/W Protection command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        sectors = self._parse_sector_list(params["sectors"])
        sector_names = ", ".join(str(s) for s in sectors)
        self.ui_queue.put({
            "type": "log", "level": "info",
            "text": f"Enabling R/W protection on sectors: {sector_names}",
        })
        self.client.enable_rw_protect(sectors)
        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": f"✅ R/W protection enabled on sectors: {sector_names}",
        })

    def _exec_disable_protect(self, params: dict) -> None:
        """Handle Disable R/W Protection command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        sectors = self._parse_sector_list(params["sectors"])
        sector_names = ", ".join(str(s) for s in sectors)
        self.ui_queue.put({
            "type": "log", "level": "info",
            "text": f"Disabling R/W protection on sectors: {sector_names}",
        })
        self.client.disable_rw_protect(sectors)
        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": f"✅ R/W protection disabled on sectors: {sector_names}",
        })

    def _exec_erase(self, params: dict) -> None:
        """Handle Erase command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        sector = params["sector"]
        count = params["count"]

        if sector == 0xFF:
            self.ui_queue.put({
                "type": "log", "level": "warning",
                "text": "⚠ WARNING: Mass erase will erase ALL flash including the bootloader!",
            })
            self.ui_queue.put({
                "type": "log", "level": "info",
                "text": "Mass erasing all flash sectors...",
            })
        else:
            if sector < 2:
                self.ui_queue.put({
                    "type": "log", "level": "warning",
                    "text": "⚠ WARNING: Sectors 0-1 are the bootloader! "
                            "Erasing them will brick the device.",
                })

            self.ui_queue.put({
                "type": "log", "level": "info",
                "text": f"Erasing sectors {sector}-{sector + count - 1}...",
            })

        self.client.flash_erase(sector, count)

        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": "✅ Erase complete",
        })

    def _exec_read(self, params: dict) -> None:
        """Handle Read command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        address = params["address"]
        length = params["length"]

        self.ui_queue.put({
            "type": "log", "level": "info",
            "text": f"Reading {length} bytes from 0x{address:08X}...",
        })

        data = self.client.mem_read(address, length)

        # Format as hex dump
        dump = self._format_hex_dump(data, address)
        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": f"Read {len(data)} bytes:\n{dump}",
        })

    def _exec_write(self, params: dict) -> None:
        """Handle Write command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        address = params["address"]
        hex_data = params.get("data_hex", "")
        file_path = params.get("file_path", "")

        if file_path and os.path.isfile(file_path):
            with open(file_path, "rb") as f:
                data = f.read()
            self.ui_queue.put({
                "type": "log", "level": "info",
                "text": f"Read {len(data)} bytes from {os.path.basename(file_path)}",
            })
        elif hex_data:
            data = self._parse_hex_bytes(hex_data)
        else:
            raise ValidationError(
                "Provide hex data or select a binary file"
            )

        self.ui_queue.put({
            "type": "log", "level": "info",
            "text": f"Writing {len(data)} bytes to 0x{address:08X}...",
        })

        if len(data) > 239:
            self.ui_queue.put({
                "type": "log", "level": "debug",
                "text": f"Payload exceeds single-write limit; sending in {DEFAULT_CHUNK_SIZE}-byte chunks...",
            })

        for offset in range(0, len(data), DEFAULT_CHUNK_SIZE):
            if self.cancel_event.is_set():
                raise _OperationCancelled()
            chunk = data[offset:offset + DEFAULT_CHUNK_SIZE]
            self.client.mem_write(address + offset, chunk)

        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": "✅ Write complete",
        })

    def _exec_send_firmware(self, params: dict) -> None:
        """Handle Send FW command — with cooperative cancellation support."""
        file_path = params["file_path"]
        if not file_path or not os.path.isfile(file_path):
            raise ValidationError(f"File not found: {file_path}")

        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return

        self.ui_queue.put({"type": "progress_show"})

        # Check cancel before each chunk via a wrapper
        def progress_with_cancel(chunk_idx: int, total_chunks: int) -> None:
            if self.cancel_event.is_set():
                raise _OperationCancelled()
            self.ui_queue.put({
                "type": "progress",
                "current": chunk_idx + 1,
                "total": total_chunks,
            })

        result = self.client.send_file(
            file_path=file_path,
            address=params["address"],
            chunk_size=params.get("chunk_size", 128),
            erase=params.get("erase", False),
            verify=params.get("verify", False),
            go=params.get("go", False),
            progress_callback=progress_with_cancel,
        )

        # Summary
        lines = ["✅ Firmware update complete:", ""]
        lines.append(f"  File:     {os.path.basename(result['file'])}")
        lines.append(f"  Path:     {result['file']}")
        lines.append(f"  Size:     {result['size']} bytes")
        lines.append(f"  Address:  0x{result['address']:08X}")
        lines.append(f"  Chunks:   {result['chunks']}")
        lines.append(f"  Sectors:  {result['sectors']}")
        lines.append(f"  Erased:   {'✓' if result['erased'] else '—'}")
        lines.append(f"  Verified: {'✓' if result['verified'] else '—'}")
        lines.append(f"  Jumped:   {'✓' if result['jumped'] else '—'}")
        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": "\n".join(lines),
        })

    def _exec_go_to(self, params: dict) -> None:
        """Handle Go To command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        address = params["address"]

        self.ui_queue.put({
            "type": "log", "level": "info",
            "text": f"Jumping to 0x{address:08X}...",
        })

        try:
            self.client.go_to_address(address)
            self.ui_queue.put({
                "type": "log", "level": "success",
                "text": "Go To command acknowledged",
            })
        except (TimeoutError, NackError) as e:
            self.ui_queue.put({
                "type": "log", "level": "warning",
                "text": f"Jump executed (expected: {e})",
            })

    def _exec_otp_read(self, params: dict) -> None:
        """Handle OTP Read command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        address = params["address"]
        length = params["length"]

        # Validate OTP address range
        if not (OTP_BASE_ADDR <= address <= OTP_END_ADDR):
            self.ui_queue.put({
                "type": "log", "level": "error",
                "text": f"Address 0x{address:08X} is outside OTP range (0x{OTP_BASE_ADDR:08X} - 0x{OTP_END_ADDR:08X})",
            })
            return

        if length <= 0 or length > 128:
            self.ui_queue.put({
                "type": "log", "level": "error",
                "text": f"Invalid read length: {length} (must be 1-128)",
            })
            return

        self.ui_queue.put({
            "type": "log", "level": "info",
            "text": f"Reading {length} bytes from OTP at 0x{address:08X}...",
        })

        data = self.client.otp_read(address, length)

        if data:
            dump = self._format_hex_dump(data, address)
            self.ui_queue.put({
                "type": "log", "level": "success",
                "text": f"OTP read {len(data)} bytes:\n{dump}",
            })
        else:
            self.ui_queue.put({
                "type": "log", "level": "warning",
                "text": "No OTP data returned",
            })

    def _exec_raw(self, params: dict) -> None:
        """Handle Raw Cmd command."""
        if self.cancel_event.is_set():
            self.ui_queue.put({"type": "log", "level": "warning",
                               "text": "Operation cancelled"})
            return
        cmd_str = params["cmd"]
        data_str = params["data"]

        cmd_byte = int(cmd_str, 16) if cmd_str.startswith("0x") else int(cmd_str)
        data_bytes = self._parse_hex_bytes(data_str) if data_str else b""

        self.ui_queue.put({
            "type": "log", "level": "info",
            "text": f"Sending raw: cmd=0x{cmd_byte:02X}, data={data_bytes.hex()}",
        })

        resp = self.client.command(cmd_byte, data_bytes)

        lines = [f"ACK received, follow_len={resp.follow_len}"]
        if resp.data:
            lines.append(f"Response data: {resp.data.hex(' ')}")
        else:
            lines.append("Response data: (empty)")

        self.ui_queue.put({
            "type": "log", "level": "success",
            "text": "\n".join(lines),
        })

    # ── Progress Handling ─────────────────────────────────────────────

    def _show_progress(self, visible: bool) -> None:
        """Show or hide the progress bar neon panel."""
        if visible:
            self.progress_glow.pack(
                fill=tk.X, side=tk.TOP,
                before=self._log_glow,
            )
        else:
            self.progress_glow.pack_forget()

    def _update_progress(self, current: int, total: int) -> None:
        """Update the progress bar value and label."""
        pct = int(current * 100 / total) if total > 0 else 0
        self.progress_bar["value"] = pct
        self.progress_bar["maximum"] = 100
        self.progress_label.configure(
            text=f"{pct}% ({current}/{total} chunks)"
        )

    # ── Queue Polling ─────────────────────────────────────────────────

    def _poll_queue(self) -> None:
        """Process messages from the worker thread (runs on main thread)."""
        try:
            while True:
                msg = self.ui_queue.get_nowait()
                self._handle_queue_message(msg)
        except queue.Empty:
            pass
        finally:
            self.after(50, self._poll_queue)

    def _handle_queue_message(self, msg: dict) -> None:
        """Dispatch a queue message to the appropriate UI update."""
        msg_type = msg.get("type", "")

        if msg_type == "log":
            self._log(msg["text"], msg.get("level", "info"))

        elif msg_type == "connected":
            self.client = msg["client"]
            self.connected = True
            self._log(
                f"Connected to {msg['port']} at {msg['baud']} baud",
                "success",
            )
            self._apply_ui_state()

        elif msg_type == "progress":
            self._update_progress(msg["current"], msg["total"])

        elif msg_type == "progress_show":
            self._show_progress(True)
            self._update_progress(0, 1)

        elif msg_type == "progress_hide":
            self._show_progress(False)

        elif msg_type == "done":
            self.busy = False
            self.cancel_event.clear()
            self._apply_ui_state()

    # ── Trace callback (raw hex frame logging) ─────────────────────────

    def _trace_client_frame(self, trace: CommandTrace) -> None:
        """
        Callback from BootloaderClient — queues raw frame data for display.
        Runs in the worker thread, so we push to the UI queue.
        """
        lines = [
            f"SENT  → {trace.request_hex}",
            f"RECV  ← {trace.response_hex}",
        ]
        if trace.error:
            lines.append(f"NOTE  · {trace.error}")

        self.ui_queue.put({
            "type": "log",
            "level": "data",
            "text": "\n".join(lines),
        })

    # ── Logging ────────────────────────────────────────────────────────

    def _clear_log(self) -> None:
        """Clear all content from the log output."""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _log(self, message: str, level: str = "info") -> None:
        """Append a timestamped message to the log widget."""
        ts = datetime.now().strftime("%H:%M:%S")
        text = f"[{ts}] {message}\n"

        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text, level)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ── Utility Methods ────────────────────────────────────────────────

    @staticmethod
    def _parse_address(s: str) -> int:
        """Parse a hex or decimal address string."""
        s = s.strip()
        if s.startswith("0x") or s.startswith("0X"):
            return int(s, 16)
        return int(s)

    @staticmethod
    def _parse_hex_bytes(s: str) -> bytes:
        """Parse a hex string into bytes, tolerating spaces."""
        s = s.strip().replace(" ", "")
        if not s:
            return b""
        return bytes.fromhex(s)

    @staticmethod
    def _format_hex_dump(data: bytes, base_addr: int = 0) -> str:
        """Format bytes as a hex dump with addresses."""
        lines = []
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            hex_part = hex_part.ljust(47)
            ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
            lines.append(f"{base_addr + i:08X}: {hex_part} {ascii_part}")
        return "\n".join(lines)

    @staticmethod
    def _parse_sector_list(s: str) -> list[int]:
        """Parse a comma or space separated list of sector numbers."""
        if not s or not s.strip():
            raise ValidationError("No sectors specified")
        sectors = []
        for part in s.replace(",", " ").split():
            part = part.strip()
            if not part:
                continue
            try:
                sector = int(part)
            except ValueError:
                raise ValidationError(
                    f"Invalid sector number: '{part}'"
                ) from None
            if not (0 <= sector <= 11):
                raise ValidationError(
                    f"Sector {sector} out of range (must be 0-11)"
                )
            if sector in (0, 1):
                raise ValidationError(
                    "Cannot modify protection for bootloader sectors 0-1"
                )
            sectors.append(sector)
        if not sectors:
            raise ValidationError("No valid sectors specified")
        return sectors

    # ── Close ──────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        """Clean up, save settings, and close the application."""
        self._save_settings()
        self._disconnect()
        self.destroy()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Launch the bootloader GUI application."""
    app = BootloaderGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
