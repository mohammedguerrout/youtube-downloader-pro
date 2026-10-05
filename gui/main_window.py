"""
gui/main_window.py
The application shell: the sidebar (settings shared by every tab), the
tab view itself, and the bottom status bar. Each tab (Download, Search,
Playlist, Queue, History) lives in its own module in this package and
reads shared settings from this window rather than duplicating them.
"""

import os
import queue
from pathlib import Path
from tkinter import END
from tkinter.filedialog import askdirectory

import customtkinter as ctk
from PIL import Image

from config import APP_TITLE, APP_VERSION, COLOR_ERROR, COLOR_INFO, COLOR_OK, COLOR_WORK, load_config, save_config
from queue_manager import DownloadQueue
from youtube_service import YouTubeSessionCache, ffmpeg_available

from gui.download_tab import DownloadTab
from gui.history_tab import HistoryTab
from gui.playlist_tab import PlaylistTab
from gui.queue_tab import QueueTab
from gui.search_tab import SearchTab

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

DISCLAIMER_TEXT = (
    "This application downloads content from YouTube for personal, offline "
    "use only. You are solely responsible for ensuring your use complies "
    "with YouTube's Terms of Service and all applicable copyright laws. "
    "Do not download or redistribute content you do not have the right to use.\n\n"
    "هذا التطبيق يحمّل محتوى من يوتيوب للاستخدام الشخصي دون اتصال بالإنترنت فقط. "
    "أنت وحدك المسؤول عن التأكد من توافق استخدامك مع شروط خدمة يوتيوب وقوانين "
    "حقوق النشر. لا تقم بتحميل أو إعادة نشر محتوى لا تملك الحق في استخدامه."
)


class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.config_data = load_config()
        ctk.set_appearance_mode(self.config_data.get("appearance", "System"))
        ctk.set_default_color_theme("dark-blue")

        self.ui_queue: queue.Queue = queue.Queue()
        self.queue_manager = DownloadQueue()
        self.session = YouTubeSessionCache(on_progress=lambda *a, **kw: None)  # Download tab fetch-preview only

        self.setup_window()
        self.build_ui()
        self.process_ui_queue()
        self.after(500, self._poll_queue_tab)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self._install_global_paste_shortcut()

        if not self.config_data.get("disclaimer_accepted", False):
            self.after(200, self.show_disclaimer)

    # ------------------------------------------------------------------
    # Window / icon
    # ------------------------------------------------------------------

    def setup_window(self):
        self.title(APP_TITLE)
        self.geometry("980x680")
        self.minsize(900, 640)
        self._apply_icon()

    def _apply_icon(self):
        ico_path = ASSETS_DIR / "icon.ico"
        png_path = ASSETS_DIR / "icon.png"
        try:
            if os.name == "nt" and ico_path.exists():
                self.iconbitmap(str(ico_path))
            elif png_path.exists():
                from PIL import ImageTk
                tk_icon = ImageTk.PhotoImage(Image.open(png_path))
                self.iconphoto(True, tk_icon)
                self._icon_ref = tk_icon
        except Exception:
            pass

    # ------------------------------------------------------------------
    # First-run disclaimer
    # ------------------------------------------------------------------

    def show_disclaimer(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Terms of Use")
        dialog.geometry("520x380")
        dialog.resizable(False, False)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="⚖️ Before you continue", font=("bold", 18)).pack(pady=(20, 10))
        textbox = ctk.CTkTextbox(dialog, width=460, height=240, wrap="word")
        textbox.insert("1.0", DISCLAIMER_TEXT)
        textbox.configure(state="disabled")
        textbox.pack(padx=20, pady=10)

        def accept():
            self.config_data["disclaimer_accepted"] = True
            save_config(self.config_data)
            dialog.destroy()

        ctk.CTkButton(dialog, text="I Understand & Agree", command=accept, fg_color=COLOR_OK).pack(pady=15)
        dialog.protocol("WM_DELETE_WINDOW", accept)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_tabs()
        self._build_status_bar()

    def _build_sidebar(self):
        side = ctk.CTkScrollableFrame(self, corner_radius=20, width=210)
        side.grid(row=0, column=0, padx=(20, 10), pady=20, sticky="ns")

        ctk.CTkLabel(side, text="⚙️ Settings", font=("bold", 18)).pack(padx=15, pady=(15, 20))

        ctk.CTkLabel(side, text="Appearance", font=("bold", 13)).pack(padx=15, pady=(5, 5))
        self.appearance_mode = ctk.CTkOptionMenu(
            side, values=["System", "Dark", "Light"], command=self.change_appearance_mode
        )
        self.appearance_mode.set(self.config_data.get("appearance", "System"))
        self.appearance_mode.pack(padx=15, pady=(0, 15))

        ctk.CTkLabel(side, text="Download Type", font=("bold", 13)).pack(padx=15, pady=(5, 5))
        self.mode_var = ctk.StringVar(value=self.config_data.get("mode", "video"))
        ctk.CTkRadioButton(
            side, text="🎬 Video", variable=self.mode_var, value="video", command=self.on_mode_change
        ).pack(padx=15, pady=4, anchor="w")
        ctk.CTkRadioButton(
            side, text="🎵 Audio Only", variable=self.mode_var, value="audio", command=self.on_mode_change
        ).pack(padx=15, pady=4, anchor="w")

        ctk.CTkLabel(side, text="Quality", font=("bold", 13)).pack(padx=15, pady=(15, 5))
        self.quality_menu = ctk.CTkOptionMenu(side, values=["Highest", "Lowest"])
        self.quality_menu.set(self.config_data.get("quality", "Highest"))
        self.quality_menu.pack(padx=15, pady=(0, 15))

        self.mp3_switch = ctk.CTkSwitch(side, text="🎵 Convert to MP3")
        if self.config_data.get("mp3", False):
            self.mp3_switch.select()
        self.mp3_switch.pack(padx=15, pady=6, anchor="w")

        self.subtitles_switch = ctk.CTkSwitch(side, text="📝 Download subtitles")
        if self.config_data.get("subtitles", False):
            self.subtitles_switch.select()
        self.subtitles_switch.pack(padx=15, pady=6, anchor="w")

        ctk.CTkLabel(side, text="Save to", font=("bold", 13)).pack(padx=15, pady=(15, 5))
        self.folder_entry = ctk.CTkEntry(side, height=32)
        self.folder_entry.insert(0, self.config_data.get("folder", str(Path.home() / "Downloads")))
        self.folder_entry.pack(padx=15, pady=(0, 5), fill="x")
        ctk.CTkButton(side, text="📁 Browse", height=28, command=self.choose_folder).pack(padx=15, pady=(0, 15), fill="x")

        self.ffmpeg_warning = ctk.CTkLabel(
            side, text="", font=("arial", 11), text_color=COLOR_WORK, wraplength=170, justify="left"
        )
        self.ffmpeg_warning.pack(padx=15, pady=(0, 10))
        if not ffmpeg_available():
            self.ffmpeg_warning.configure(
                text="⚠️ Video processor unavailable right now. "
                     "Videos above 360p may download without sound until it's ready."
            )

        ctk.CTkLabel(side, text=f"v{APP_VERSION}", font=("arial", 10), text_color="gray").pack(pady=10)

        self.on_mode_change()

    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self, corner_radius=20)
        self.tabview.grid(row=0, column=1, padx=(10, 20), pady=20, sticky="nsew")

        self.tabview.add("⬇️ Download")
        self.tabview.add("🔍 Search")
        self.tabview.add("📃 Playlist")
        self.tabview.add("📥 Queue")
        self.tabview.add("🕘 History")

        self.download_tab = DownloadTab(self.tabview.tab("⬇️ Download"), self)
        self.download_tab.pack(fill="both", expand=True)

        self.search_tab = SearchTab(self.tabview.tab("🔍 Search"), self)
        self.search_tab.pack(fill="both", expand=True)

        self.playlist_tab = PlaylistTab(self.tabview.tab("📃 Playlist"), self)
        self.playlist_tab.pack(fill="both", expand=True)

        self.queue_tab = QueueTab(self.tabview.tab("📥 Queue"), self)
        self.queue_tab.pack(fill="both", expand=True)

        self.history_tab = HistoryTab(self.tabview.tab("🕘 History"), self)
        self.history_tab.pack(fill="both", expand=True)

    def _build_status_bar(self):
        self.status_label = ctk.CTkLabel(self, text="", font=("bold", 12), anchor="w")
        self.status_label.grid(row=1, column=0, columnspan=2, padx=25, pady=(0, 10), sticky="ew")

    # ------------------------------------------------------------------
    # Shared helpers used by every tab
    # ------------------------------------------------------------------

    def ui(self, func, *args, **kwargs):
        """Thread-safe way for background threads to schedule UI updates."""
        self.ui_queue.put((func, args, kwargs))

    def process_ui_queue(self):
        try:
            while True:
                func, args, kwargs = self.ui_queue.get_nowait()
                func(*args, **kwargs)
        except queue.Empty:
            pass
        self.after(50, self.process_ui_queue)

    def set_status(self, text: str, color: str = COLOR_INFO):
        self.status_label.configure(text=text, text_color=color)

    def go_to_queue_tab(self):
        self.tabview.set("📥 Queue")

    def _poll_queue_tab(self):
        self.queue_tab.refresh()
        self.after(500, self._poll_queue_tab)

    # ------------------------------------------------------------------
    # App-wide Ctrl+V (works in every text field, on every keyboard layout)
    # ------------------------------------------------------------------

    def _install_global_paste_shortcut(self):
        """Binds Ctrl+V once, for the whole application, instead of once
        per text field. This matters specifically for non-US keyboard
        layouts (Arabic, French AZERTY, ...): Tkinter's own built-in
        paste binding — and a naive `widget.bind('<Control-v>', ...)` —
        both rely on the *keysym* 'v', which on many non-US layouts is
        not what the physical V key actually reports when Ctrl is held.
        `event.keycode` instead reflects the *physical* key position
        (VK_V = 86 on Windows, consistent across layouts), which is what
        we check here as the reliable fallback.

        Tk's own built-in paste action lives on the widget *class*
        bindtag (e.g. "Entry", "Text") as a binding to the virtual
        event "<<Paste>>" — not to "<Control-v>" directly, a physical
        key combination is merely *mapped* to that virtual event
        elsewhere. The class-level "<<Paste>>" binding fires *before*
        an "all" bindtag handler like ours, so without removing it
        first, a successful paste from our handler runs right after
        Tk's own, pasting the clipboard content twice. We remove the
        "<<Paste>>" class binding itself so our handler is the only
        thing that actually performs the paste, on any layout."""
        for widget_class in ("Entry", "Text"):
            try:
                self.unbind_class(widget_class, "<<Paste>>")
            except Exception:
                pass
        self.bind_all("<Control-Key>", self._global_paste_handler, add="+")

    def _global_paste_handler(self, event):
        is_v_key = (event.keysym.lower() == "v") or (os.name == "nt" and event.keycode == 86)
        if not is_v_key:
            return  # some other Ctrl+<key> combo — not ours to handle

        widget = event.widget
        try:
            clipboard_content = self.clipboard_get()
        except Exception:
            return  # nothing on the clipboard (or it's not text) — nothing to paste

        try:
            if widget.selection_present():
                widget.delete("sel.first", "sel.last")
        except Exception:
            pass  # widget has no selection concept (or nothing selected) — fine

        try:
            widget.insert("insert", clipboard_content)
        except Exception:
            return  # the focused widget isn't a text field (e.g. a button) — let it be

        return "break"  # prevents Tkinter's own default paste binding from firing too

    # ------------------------------------------------------------------
    # Sidebar events
    # ------------------------------------------------------------------

    def on_mode_change(self):
        is_audio = self.mode_var.get() == "audio"
        self.quality_menu.configure(state="disabled" if is_audio else "normal")
        self.mp3_switch.configure(state="normal" if is_audio else "disabled")
        self.subtitles_switch.configure(state="disabled" if is_audio else "normal")

    def choose_folder(self):
        path = askdirectory(title="Select Save Folder", initialdir=self.folder_entry.get() or None)
        if path:
            self.folder_entry.delete(0, END)
            self.folder_entry.insert(0, path)

    def change_appearance_mode(self, mode):
        ctk.set_appearance_mode(mode)

    def on_close(self):
        self.config_data.update({
            "folder": self.folder_entry.get().strip(),
            "appearance": self.appearance_mode.get(),
            "mode": self.mode_var.get(),
            "quality": self.quality_menu.get(),
            "mp3": bool(self.mp3_switch.get()),
            "subtitles": bool(self.subtitles_switch.get()),
        })
        save_config(self.config_data)
        self.destroy()
