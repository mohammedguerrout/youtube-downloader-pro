"""
gui/history_tab.py
The "History" tab: every successfully completed download (video,
audio, mp3, subtitles), persisted across sessions, with quick access
to the file and its folder.
"""

import os

import customtkinter as ctk

import history
from config import COLOR_ERROR, COLOR_OK, COLOR_WORK
from utils import format_size

KIND_ICONS = {"video": "🎬", "audio": "🎵", "mp3": "🎵", "subtitles": "📝"}


class HistoryTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="🕘 Download History", font=("bold", 22)).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="🔄 Refresh", width=100, command=self.refresh).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            header, text="🗑️ Clear all", width=100, fg_color=COLOR_ERROR, hover_color="#a93034",
            command=self.clear_all,
        ).grid(row=0, column=2)

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        entries = history.load_history()
        if not entries:
            ctk.CTkLabel(self.list_frame, text="No downloads yet.", text_color="gray").pack(pady=30)
            return

        for index, entry in enumerate(entries):
            self._build_row(index, entry)

    def _build_row(self, index, entry):
        row = ctk.CTkFrame(self.list_frame, corner_radius=12)
        row.pack(fill="x", pady=6)
        row.grid_columnconfigure(0, weight=1)

        icon = KIND_ICONS.get(entry.get("kind"), "📄")
        ctk.CTkLabel(
            row, text=f"{icon} {entry.get('title', 'Unknown')}", font=("bold", 13),
            anchor="w", wraplength=460,
        ).grid(row=0, column=0, columnspan=3, padx=12, pady=(10, 2), sticky="ew")

        size_text = format_size(entry.get("size", 0))
        ctk.CTkLabel(
            row, text=f"{entry.get('date', '')}   •   {size_text}", font=("arial", 11), text_color="gray",
            anchor="w",
        ).grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")

        ctk.CTkButton(
            row, text="📂 Open folder", width=120, height=28,
            command=lambda e=entry: self._open_folder(e),
        ).grid(row=1, column=1, padx=5, pady=(0, 10))

        ctk.CTkButton(
            row, text="🗑️", width=36, height=28, fg_color=COLOR_ERROR, hover_color="#a93034",
            command=lambda i=index: self._remove(i),
        ).grid(row=1, column=2, padx=(5, 12), pady=(0, 10))

    def _open_folder(self, entry):
        path = entry.get("path", "")
        folder = os.path.dirname(path) if path else ""
        if not folder or not os.path.isdir(folder):
            self.app.set_status("This folder no longer exists.", COLOR_ERROR)
            return
        try:
            if os.name == "nt":
                os.startfile(folder)
            elif os.uname().sysname == "Darwin":
                os.system(f'open "{folder}"')
            else:
                os.system(f'xdg-open "{folder}"')
        except Exception:
            self.app.set_status("Could not open the folder.", COLOR_ERROR)

    def _remove(self, index):
        history.remove_entry(index)
        self.refresh()

    def clear_all(self):
        history.clear_history()
        self.refresh()
        self.app.set_status("History cleared.", COLOR_OK)
