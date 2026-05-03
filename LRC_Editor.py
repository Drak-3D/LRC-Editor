import sys
import os
import time
import tempfile
import subprocess
import re
import io
import json
import shutil
import webbrowser
import bisect
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

# =============================================================================
# DEPENDENCY CHECK
# =============================================================================
missing_libs = []

try:
    import vlc
except ImportError:
    missing_libs.append("python-vlc")

try:
    from mutagen.id3 import (
        ID3, APIC, USLT, TIT2, TPE1, TPE2, TALB, TYER, TDRC, TRCK, TCON, 
        TCOM, TPUB, TCOP, TPOS, TBPM, TKEY, TOPE, TPE4, TPE3, TIT1, TIT3, 
        TSRC, TENC, COMM, TXXX
    )
    from mutagen.flac import Picture
    from mutagen import File
except ImportError:
    missing_libs.append("mutagen")

try:
    from PIL import Image, ImageTk
except ImportError:
    missing_libs.append("pillow")

# If any libraries are missing, show a user-friendly error window
if missing_libs:
    error_window = tk.Tk()
    error_window.title("Missing Requirements")
    error_window.geometry("550x350")
    error_window.config(bg="#050505")
    
    tk.Label(
        error_window, 
        text="Missing Libraries!", 
        font=("Segoe UI", 16, "bold"), 
        bg="#050505", 
        fg="#ff4444"
    ).pack(pady=(20, 10))
    
    def copy_to_clipboard(event, command_text):
        """Copies the pip install command to the system clipboard."""
        error_window.clipboard_clear()
        error_window.clipboard_append(command_text)
        label_widget = event.widget
        original_text = label_widget.cget("text")
        label_widget.config(text="Copied!", fg="#42f542")
        error_window.after(1000, lambda: label_widget.config(text=original_text, fg="#00ffc3"))
        
    for lib in missing_libs:
        install_command = f"pip install {lib}"
        lbl = tk.Label(
            error_window, 
            text=install_command, 
            font=("Consolas", 14, "bold"), 
            bg="#222", 
            fg="#00ffc3", 
            cursor="hand2", 
            padx=10, 
            pady=5
        )
        lbl.pack(pady=5)
        lbl.bind("<Double-Button-1>", lambda e, cmd=install_command: copy_to_clipboard(e, cmd))
        
    tk.Button(
        error_window, 
        text="Exit", 
        command=error_window.destroy, 
        width=15, 
        bg="#444", 
        fg="white"
    ).pack(pady=20)
    
    error_window.mainloop()
    sys.exit()

# =============================================================================
# CONSTANTS & CONFIGURATION
# =============================================================================

# Determine the application directory (handles frozen PyInstaller executables)
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APP_DIR, "lrc_shifter_config.json")
HIDDEN_GIMMICKS_FILE = os.path.join(APP_DIR, "HiddenGimmicks.txt")

# Regular expressions for parsing LRC timestamps and URLs
LRC_REGEX = re.compile(r"\[(\d{2}):(\d{2})\.(\d+)\]")
URL_REGEX = re.compile(r'https?://\S+')

# Default application settings
DEFAULT_SETTINGS = {
    "theme": "OLED",
    "active_bg": "#00ffc3",
    "active_fg": "#000000",
    "active_bold": True,
    "played_bg": "#42f542",
    "played_fg": "#000000",
    "played_bold": False,
    "count_bg": "#ff0000",
    "count_fg": "#ffffff",
    "count_bold": True,
    "thumb_size": 200,
    "offset_sign": "+",
    "inv_scroll_time": False,
    "inv_scroll_line": False,
    "volume": 75,
    "first_run": True,
    "auto_open_saved": True,
    "show_tooltips": False,
    "meta_main": ["Title", "Artist", "Album", "Track", "Disc", "Year", "Genre"],
    "last_search": "",
    "default_music_dir": "",
    "slider_sync": True,
    "slider_bg": "#1a1a1a",
    "slider_played": "#42f542",
    "slider_thumb": "#00ffc3",
    "slider_thumb_border": "#000000",
    "sync_offset": 0,
    "sync_bg": "#ffaa00",
    "sync_fg": "#000000",
    "sync_bold": True,
    "hotkeys": {
        "open_audio": {"bind": "Ctrl+A", "desc": "Open Audio", "enabled": True},
        "save_audio": {"bind": "Ctrl+Shift+A", "desc": "Save Audio Meta", "enabled": True},
        "save_audio_as": {"bind": "Ctrl+Alt+A", "desc": "Save Audio As...", "enabled": True},
        "open_lrc": {"bind": "Ctrl+L", "desc": "Open LRC File", "enabled": True},
        "save_lrc": {"bind": "Ctrl+Shift+L", "desc": "Save LRC", "enabled": True},
        "save_lrc_as": {"bind": "Ctrl+Alt+L", "desc": "Save LRC As...", "enabled": True},
        "import_lrc": {"bind": "Ctrl+I", "desc": "Import LRC from Audio", "enabled": True},
        "open_image": {"bind": "Ctrl+P", "desc": "Open Image Cover", "enabled": True},
        "exit": {"bind": "Alt+C", "desc": "Exit Program", "enabled": True},
        "play_pause": {"bind": "Alt+P", "desc": "Play/Pause (Alt+P, S, Space)", "enabled": True},
        "seek_back": {"bind": "Alt+A", "desc": "Seek -5s (Alt+A)", "enabled": True},
        "seek_fwd": {"bind": "Alt+D", "desc": "Seek +5s (Alt+D)", "enabled": True},
        "seek_back_1": {"bind": "X", "desc": "Seek -1s (X)", "enabled": True},
        "nav_up": {"bind": "Up", "desc": "Prev Line No Seek (Up, Z)", "enabled": True},
        "nav_down": {"bind": "Down", "desc": "Next Line No Seek (Down, C)", "enabled": True},
        "nav_left": {"bind": "Left", "desc": "Prev Line & Seek (Left, A)", "enabled": True},
        "nav_right": {"bind": "Right", "desc": "Next Line & Seek (Right, D)", "enabled": True},
        "stamp_sync": {"bind": "Return", "desc": "Stamp Time (Enter)", "enabled": True},
        "view_file": {"bind": "Alt+J", "desc": "View LRC File", "enabled": True},
        "view_meta": {"bind": "Alt+M", "desc": "View Metadata", "enabled": True},
        "toggle_scroll": {"bind": "Alt+X", "desc": "Toggle Auto-scroll", "enabled": True},
        "appearance": {"bind": "Alt+Z", "desc": "Appearance", "enabled": True},
        "reset_off": {"bind": "Alt+R", "desc": "Reset Offsets", "enabled": True},
        "add_min": {"bind": "Alt+Q", "desc": "+1 Min / -10ms Sync", "enabled": True},
        "add_sec": {"bind": "Alt+W", "desc": "+1 Sec / -10ms Sync", "enabled": True},
        "add_ms": {"bind": "Alt+E", "desc": "+1 MS / -10ms Sync", "enabled": True},
        "sync_mode": {"bind": "Ctrl+E", "desc": "Sync from Scratch", "enabled": True},
        "escape": {"bind": "Escape", "desc": "Close Windows / Cancel Sync", "enabled": True},
        "theme_w": {"bind": "Shift+Alt+W", "desc": "Theme White", "enabled": True},
        "theme_g": {"bind": "Shift+Alt+G", "desc": "Theme Gray", "enabled": True},
        "theme_o": {"bind": "Shift+Alt+O", "desc": "Theme OLED", "enabled": True}
    }
}

# Grouping for the hotkeys window
HOTKEY_GROUPS = {
    "Playback & Navigation": [
        "play_pause", "seek_back", "seek_fwd", "seek_back_1", 
        "nav_up", "nav_down", "nav_left", "nav_right"
    ],
    "Sync Mode (Ctrl+E)": [
        "sync_mode", "stamp_sync", "escape"
    ],
    "File Operations": [
        "open_audio", "save_audio", "save_audio_as", "open_lrc", 
        "save_lrc", "save_lrc_as", "import_lrc", "open_image", "exit"
    ],
    "Offsets Adjustment": [
        "reset_off", "add_min", "add_sec", "add_ms"
    ],
    "Appearance & Tools": [
        "view_file", "view_meta", "toggle_scroll", "appearance", 
        "theme_w", "theme_g", "theme_o"
    ]
}

META_ORDER = [
    "Title", "Artist", "Album Artist", "Album", "Track", "Disc", "Year", 
    "Genre", "BPM", "Key", "Original Artist", "Remixed by", "Composer", 
    "Conductor", "Grouping", "Subtitle", "ISRC", "Publisher", "Copyright", 
    "URL", "Encoded by", "Comment"
]

GENRES = [
    "Pop", "Rock", "Hip-Hop", "Electronic", "R&B", "Country", "Jazz", 
    "Classical", "Metal", "Blues", "Reggae", "Folk", "Soundtrack", 
    "Alternative", "Indie", "Dance"
]

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_colors(theme_name):
    """Returns a tuple of hex color codes based on the selected theme."""
    if theme_name == "White":
        return "#ffffff", "#000000", "#f5f5f5", "#cccccc"
    if theme_name == "Gray":
        return "#1e1e1e", "#e0e0e0", "#2d2d2d", "#3d3d3d"
    # Default to OLED
    return "#000000", "#e0e0e0", "#050505", "#222222"

def get_contrast(hex_col):
    """Calculates the best contrasting text color (black or white) for a given hex background."""
    hex_col = hex_col.lstrip('#')
    if len(hex_col) != 6:
        return "#000000"
    r, g, b = tuple(int(hex_col[i:i+2], 16) for i in (0, 2, 4))
    # Luminance formula
    if ((0.299 * r + 0.587 * g + 0.114 * b) / 255) > 0.5:
        return "#000000"
    else:
        return "#ffffff"

def parse_hk(s):
    """Converts standard shortcut strings into Tkinter event bindings."""
    # Special single key binds mapping
    if s in ["A", "D", "Z", "C", "X", "S", "Up", "Down", "Left", "Right", "Return", "Escape"]:
        return f"<{s}>"
        
    parts = [x.strip().lower() for x in s.split("+")]
    key = parts[-1]
    modifiers = []
    
    if "ctrl" in parts:
        modifiers.append("Control")
    if "alt" in parts:
        modifiers.append("Alt")
    if "shift" in parts:
        modifiers.append("Shift")
        # Capitalize single letter if Shift is present
        if len(key) == 1:
            key = key.upper()
            
    if key == "space":
        key = "space"
        
    if key:
        modifier_prefix = '-'.join(modifiers) + '-' if modifiers else ''
        return f"<{modifier_prefix}{key}>"
    return ""

def center_window(win):
    """Centers a Tkinter window on the display screen."""
    win.update_idletasks()
    width = win.winfo_width()
    height = win.winfo_height()
    x = (win.winfo_screenwidth() // 2) - (width // 2)
    y = (win.winfo_screenheight() // 2) - (height // 2)
    win.geometry(f"+{x}+{y}")

# =============================================================================
# MAIN APPLICATION CLASS
# =============================================================================

class LRCTimeShifter:
    def __init__(self, root):
        self.root = root
        self.root.title("LRC Editor")
        self.root.geometry("1450x950")
        self.root.option_add('*tearOff', False)
        
        # Maximize window if possible
        try:
            self.root.state('zoomed')
        except Exception:
            self.root.attributes('-zoomed', True)
            
        self.open_windows = {}
        self.sub_windows = []
        self.local_offsets = {}
        self.line_tracker = []
        
        # Load program icons if available
        try:
            if os.path.exists(os.path.join(APP_DIR, "ProgramThumbnail.png")):
                icon_image = ImageTk.PhotoImage(Image.open(os.path.join(APP_DIR, "ProgramThumbnail.png")))
                self.root.iconphoto(True, icon_image)
            if os.path.exists(os.path.join(APP_DIR, "ProgramThumbnail.ico")):
                self.root.iconbitmap(os.path.join(APP_DIR, "ProgramThumbnail.ico"))
        except Exception:
            pass
            
        # Load settings from JSON
        self.settings = DEFAULT_SETTINGS.copy()
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded_data = json.load(f)
                    for key, value in loaded_data.items():
                        if key == "hotkeys":
                            for hk, hv in value.items():
                                self.settings["hotkeys"].get(hk, {}).update(hv)
                        else:
                            self.settings[key] = value
            except Exception:
                pass
                
        # State variables
        self.audio_path = ""
        self.lrc_path = ""
        self.lrc_from_file = ""
        self.lrc_from_meta = ""
        
        self.current_art_data = None
        self.pending_cover_data = None
        self.pending_metadata = {}
        self.metadata_edited = False
        
        # VLC Player initialization
        self.instance = vlc.Instance("--no-video --quiet")
        self.player = None
        
        # Playback tracking variables
        self.duration = 0.0
        self.last_drawn_curr = -1
        self.last_act_orig = -1
        self.last_act_shft = -1
        self.last_vlc_time = 0.0
        self.last_os_time = 0.0
        self.interpolated_time = 0.0
        
        self.is_loading = False
        self.is_seeking = False
        self.loop_track = False
        self.in_sync_mode = False
        self.sync_current_line = 0
        
        self.auto_scroll_orig = tk.BooleanVar(value=True)
        self.auto_scroll_shft = tk.BooleanVar(value=True)
        
        self.orig_ts = []
        self.shft_ts = []
        self.search_results = []
        self.current_search_idx = -1
        self.has_time_errors = False
        
        self.orig_time_errors = set()
        self.shft_time_errors = set()
        
        # GUI StringVars
        self.off_m_var = tk.StringVar(value="0")
        self.off_s_var = tk.StringVar(value="0")
        self.off_ms_var = tk.StringVar(value="0")
        
        self.ctx_menu = None
        self.ctx_m_var = tk.StringVar(value="0")
        self.ctx_s_var = tk.StringVar(value="0")
        self.ctx_ms_var = tk.StringVar(value="0")
        self.ctx_sign = tk.StringVar(value="+")
        
        self.ctx_sel_range = (0, 0)
        self.temp_local_offsets = {}
        self.ctx_sign_btn = None
        self.true_original_text = ""
        
        # Initialize User Interface
        self.setup_ui()
        self.setup_menu()
        self.apply_theme(self.settings["theme"])
        self.bind_all_hotkeys()
        
        # Core hardcoded event bindings
        self.root.bind_all("<Alt_L>", lambda e: "break")
        self.root.bind_all("<Alt_R>", lambda e: "break")
        self.root.bind("<MouseWheel>", self.on_global_scroll)
        self.root.bind_all("<Shift-MouseWheel>", self.on_shift_scroll)
        
        # Global Space and Enter binds
        self.root.bind_all("<space>", self._global_space, add="+")
        self.root.bind_all("<Return>", self._global_enter, add="+")
        self.root.bind_all("<Escape>", self.on_escape, add="+")
        
        # Dedicated Playback & Navigation Binds
        self.root.bind_all("<s>", lambda e: [self.toggle_playback(), "break"][1])
        self.root.bind_all("<S>", lambda e: [self.toggle_playback(), "break"][1])
        self.root.bind_all("<x>", lambda e: [self.seek_relative(-1), "break"][1])
        self.root.bind_all("<X>", lambda e: [self.seek_relative(-1), "break"][1])
        
        for k in ["<a>", "<A>", "<Left>"]: 
            self.root.bind_all(k, lambda e: self._nav_seek(-1))
        for k in ["<d>", "<D>", "<Right>"]: 
            self.root.bind_all(k, lambda e: self._nav_seek(1))
        for k in ["<z>", "<Z>", "<Up>"]: 
            self.root.bind_all(k, lambda e: self._nav_up())
        for k in ["<c>", "<C>", "<Down>"]: 
            self.root.bind_all(k, lambda e: self._nav_down())

        for k in ["<Alt-minus>", "<Alt-KP_Subtract>"]: 
            self.root.bind_all(k, lambda e: [self._set_sign("-"), "break"][1])
        for k in ["<Alt-plus>", "<Alt-equal>", "<Alt-KP_Add>"]: 
            self.root.bind_all(k, lambda e: [self._set_sign("+"), "break"][1])
            
        self.root.bind_all("<Control-f>", lambda e: [self.smart_search(), "break"][1])
        self.root.bind_all("<Control-h>", lambda e: [self.toggle_hk(), "break"][1])
        self.root.bind_all("<Alt-h>", lambda e: [self.toggle_hk(), "break"][1])
        self.root.bind_all("<Control-s>", lambda e: [self.toggle_files_window(), "break"][1])
        
        # Focus dropping when clicking outside of context menus
        def drop_focus(e):
            if self.ctx_menu and self.ctx_menu.winfo_exists() and not str(e.widget).startswith(str(self.ctx_menu)): 
                self.close_ctx_menu(cancel=True)
            if e.widget in [self.root, self.top_area, self.right_top_area, self.info_panel, self.work_area, self.ctrl, self.fn_f, self.src_f, self.timer_frame]:
                self.root.focus_set()
                if self.search_frame.winfo_viewable(): 
                    self.clear_search_highlight()
                    
        self.root.bind_all("<Button-1>", drop_focus, add="+")
        
        if self.settings.get("first_run", True): 
            self.settings["first_run"] = False
            self.save_settings()
            self.root.after(500, self.show_first_run)
            
        # Start main processing loop
        self.update_loop()

    # =========================================================================
    # CORE APPLICATION METHODS
    # =========================================================================

    def save_settings(self):
        """Saves current settings to the configuration JSON file."""
        try:
            with open(CONFIG_FILE, "w") as f:
                f.write(json.dumps(self.settings))
        except Exception:
            pass

    def load_cover_image_shortcut(self, e=None):
        """Allows quick loading of an image cover to pending metadata."""
        if not self.audio_path:
            return messagebox.showinfo("No Audio", "Please open an audio file first to load a cover image.")
        if p := filedialog.askopenfilename(filetypes=[("Images", "*.jpg *.jpeg *.png")]):
            try:
                with open(p, "rb") as file:
                    self.pending_cover_data = file.read()
                self.set_metadata_edited()
                messagebox.showinfo("Cover Image Loaded", "Cover image successfully added! It will be applied when you save the audio file.")
            except Exception:
                pass

    def _get_init_dir(self):
        """Determines the initial directory for file dialogs based on priority."""
        if self.audio_path: 
            return os.path.dirname(self.audio_path)
        elif self.lrc_path: 
            return os.path.dirname(self.lrc_path)
        else:
            d = self.settings.get("default_music_dir", "")
            if d and os.path.exists(d):
                return d
            return os.path.join(os.path.expanduser('~'), 'Music')

    def smart_search(self, e=None):
        """Captures text selection and initiates a search."""
        if getattr(self, 'in_sync_mode', False): 
            return
        try:
            widget = self.root.focus_get()
            if isinstance(widget, tk.Text):
                selection = widget.get(tk.SEL_FIRST, tk.SEL_LAST).strip()
                if selection:
                    self.search_entry.delete(0, tk.END)
                    self.search_entry.insert(0, selection)
                    if not self.search_frame.winfo_viewable(): 
                        self.toggle_search()
                    self.run_search()
                    return
        except tk.TclError:
            pass
        self.toggle_search()

    def toggle_hk(self, e=None):
        """Toggles the Hotkeys window."""
        if "hotkeys" in self.open_windows and self.open_windows["hotkeys"].winfo_exists(): 
            self.open_windows["hotkeys"].destroy()
        else: 
            self.open_hotkeys()

    def toggle_files_window(self, e=None):
        """Toggles the File Management window."""
        if "files" in self.open_windows and self.open_windows["files"].winfo_exists(): 
            self.open_windows["files"].destroy()
        else: 
            self.open_files()

    def toggle_search(self, e=None):
        """Toggles the inline search frame visibility."""
        if getattr(self, 'in_sync_mode', False): 
            return
        if self.search_frame.winfo_viewable(): 
            self.search_frame.pack_forget()
            self.clear_search_highlight()
            self.root.focus_set()
        else: 
            self.search_frame.pack(side="left", padx=15)
            self.search_entry.focus_set()

    def apply_theme(self, name):
        """Applies chosen color theme across all GUI elements."""
        self.settings["theme"] = name
        self.save_settings()
        
        bg_col, fg_col, box_col, track_col = get_colors(name)
        self.root.config(bg=bg_col)
        
        frames_to_bg = [
            self.top_area, self.right_top_area, self.info_panel, 
            self.timer_frame, self.ctrl, self.work_area, 
            self.art_frame, self.fn_f, self.search_frame, self.nav_f
        ]
        for f in frames_to_bg: 
            f.config(bg=bg_col)
            
        labels_to_style = [
            self.art_label, self.audio_name_lab, self.edited_lbl, 
            self.audio_path_lab, self.lrc_name_lab, self.lrc_path_lab, 
            self.tech_info_lab, self.time_label, self.timer_msg
        ]
        for l in labels_to_style: 
            if l != self.edited_lbl:
                l.config(bg=bg_col, fg=fg_col)
            else:
                l.config(bg=bg_col, fg="#ff4444")
                
        self.tech_info_lab.config(fg=fg_col if name != "White" else "#333")
        self.seek_canvas.config(bg=bg_col)
        self.src_f.config(bg=bg_col)
        
        # Configure scrollbar style
        ttk.Style().theme_use('default')
        ttk.Style().configure("TScrollbar", background=box_col, troughcolor=bg_col, arrowcolor=fg_col, bordercolor=bg_col)
        
        for rb in [self.rb1, self.rb2]: 
            rb.config(bg=bg_col, fg=fg_col, selectcolor=box_col, activebackground=bg_col, activeforeground=fg_col)
            
        # Style general control widgets
        for w in self.ctrl.winfo_children() + self.search_frame.winfo_children() + self.nav_f.winfo_children():
            if getattr(w, "custom_tag", "") == "exit_sync": 
                continue
            if isinstance(w, tk.Label): 
                w.config(bg=bg_col, fg=fg_col)
            elif isinstance(w, tk.Button): 
                w.config(bg=box_col, fg=fg_col, activebackground=track_col, activeforeground=fg_col)
            elif isinstance(w, tk.Entry): 
                w.config(bg=box_col, fg=fg_col, insertbackground=fg_col)
                
        self.btn_play.config(bg=box_col, fg=fg_col, activebackground=track_col, activeforeground=fg_col)
        if hasattr(self, 'btn_loop'): 
            self.btn_loop.config(bg=box_col, fg="#42f542" if getattr(self, 'loop_track', False) else fg_col, activebackground=track_col, activeforeground=fg_col)
            
        self.sign_btn.config(text=self.settings["offset_sign"], bg="#44ff44" if self.settings["offset_sign"]=="+" else "#ff4444", fg="black", activebackground=track_col, activeforeground="black")
        self.vol_scale.config(bg=bg_col, fg=fg_col, troughcolor=track_col, activebackground=bg_col)
        
        cols = [self.left_col, self.right_col]
        if hasattr(self, 'sync_col'): 
            cols.append(self.sync_col)
            
        for col in cols:
            col["frame"].config(bg=bg_col)
            col["t_f"].config(bg=bg_col)
            col["gut"].config(bg=bg_col)
            col["txt"].config(bg=box_col, fg=fg_col, insertbackground=fg_col)
            col["char_lbl"].config(bg=bg_col, fg=fg_col if name != "White" else "#555")
            
            for c in col["t_f"].winfo_children(): 
                if getattr(c, "custom_tag", "") == "exit_sync": 
                    continue
                if isinstance(c, tk.Checkbutton): 
                    c.config(bg=bg_col, fg=fg_col, activebackground=bg_col, selectcolor=box_col)
                elif isinstance(c, tk.Spinbox): 
                    c.config(bg=box_col, fg=fg_col, insertbackground=fg_col)
                elif isinstance(c, tk.Button): 
                    c.config(bg=box_col, fg=fg_col, activebackground=track_col, activeforeground=fg_col)
                else: 
                    c.config(bg=bg_col, fg=fg_col)
                    
            # Set up text tags for highlighting
            active_font = ("Consolas", 12, "bold" if self.settings.get("active_bold", True) else "normal")
            played_font = ("Consolas", 12, "bold" if self.settings.get("played_bold", False) else "normal")
            
            col["txt"].tag_config("active", background=self.settings["active_bg"], foreground=self.settings["active_fg"], font=active_font)
            col["txt"].tag_config("played", background=self.settings["played_bg"], foreground=self.settings["played_fg"], font=played_font)
            col["txt"].tag_config("search_all", background="#555", foreground="#fff")
            col["txt"].tag_config("search_cur", background="#ffeb3b", foreground="black")
            col["txt"].tag_config(tk.SEL, background="#0055ff", foreground="white")
            col["txt"].tag_raise(tk.SEL)
            col["txt"].tag_config("time_err", background="#ff4444", foreground="white")
            
            if col == getattr(self, 'sync_col', None):
                sync_font = ("Consolas", 12, "bold" if self.settings.get("sync_bold", True) else "normal")
                col["txt"].tag_config(
                    "sync_hl", 
                    background=self.settings.get("sync_bg", "#ffaa00"), 
                    foreground=self.settings.get("sync_fg", "#000000"), 
                    font=sync_font
                )

        self.refresh_thumbnail()
        if hasattr(self, 'seek_canvas'): 
            self._draw_seek(self.interpolated_time)
            
        for win in self.sub_windows:
            if win.winfo_exists() and getattr(win, "custom_tag", "") != "ignore_theme" and hasattr(win, "custom_refresh"): 
                win.custom_refresh(bg_col, fg_col, box_col, track_col)

    def bind_all_hotkeys(self):
        """Binds defined hotkeys to specific application methods."""
        # Unbind previous keys safely
        for s in self.settings["hotkeys"].values():
            if p := parse_hk(s["bind"]):
                try: 
                    self.root.unbind_all(p)
                except Exception: 
                    pass
                    
        actions_map = {
            "open_audio": self.load_audio, 
            "save_audio": self.save_audio, 
            "save_audio_as": self.save_audio_as, 
            "open_lrc": self.load_lrc_file, 
            "import_lrc": self.import_lrc_from_audio, 
            "open_image": self.load_cover_image_shortcut, 
            "save_lrc": self.save_lrc, 
            "save_lrc_as": self.save_lrc_as, 
            "exit": lambda: self.root.quit(), 
            "play_pause": self.toggle_playback, 
            "seek_back": lambda: self.seek_relative(-5), 
            "seek_fwd": lambda: self.seek_relative(5), 
            "view_file": lambda: [self.src_var.set("file"), self.refresh_views()], 
            "view_meta": lambda: [self.src_var.set("meta"), self.refresh_views()], 
            "toggle_scroll": self.toggle_all_autoscroll, 
            "appearance": self.open_appearance, 
            "reset_off": self.reset_offset, 
            "add_min": self.add_min, 
            "add_sec": self.add_sec, 
            "add_ms": self.add_ms, 
            "sync_mode": self.toggle_sync_mode, 
            "theme_w": lambda: self.apply_theme("White"), 
            "theme_g": lambda: self.apply_theme("Gray"), 
            "theme_o": lambda: self.apply_theme("OLED")
        }
        
        try: 
            self.root.bind_all("<Control-space>", lambda e: [actions_map["play_pause"](), "break"][1])
        except Exception: 
            pass
        try: 
            self.root.bind_all("<Alt-space>", lambda e: [actions_map["play_pause"](), "break"][1])
        except Exception: 
            pass
        
        # Iterates and sets active bind_all
        for key, conf in self.settings["hotkeys"].items():
            if conf["enabled"] and conf["bind"] and (p := parse_hk(conf["bind"])) and key in actions_map:
                try: 
                    self.root.bind_all(p, lambda e, func=actions_map[key]: [func(), "break"][1])
                except Exception: 
                    pass

    def setup_menu(self):
        """Creates the main window menubar."""
        self.root.option_add('*Menu.useMenu', 0)
        menubar = tk.Menu(self.root)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        hk = self.settings.get("hotkeys", {})
        
        def get_hk_string(k): 
            return hk.get(k, {}).get("bind", "")
        
        # Basic File operations
        file_menu.add_command(label="Open Audio", accelerator=get_hk_string('open_audio'), command=self.load_audio)
        file_menu.add_command(label="Save Audio", accelerator=get_hk_string('save_audio'), command=self.save_audio)
        file_menu.add_command(label="Save Audio As...", accelerator=get_hk_string('save_audio_as'), command=self.save_audio_as)
        file_menu.add_separator()
        
        file_menu.add_command(label="Open LRC", accelerator=get_hk_string('open_lrc'), command=self.load_lrc_file)
        file_menu.add_command(label="Import LRC from Audio...", accelerator=get_hk_string('import_lrc'), command=self.import_lrc_from_audio)
        file_menu.add_command(label="Save LRC", accelerator=get_hk_string('save_lrc'), command=self.save_lrc)
        file_menu.add_command(label="Save LRC As...", accelerator=get_hk_string('save_lrc_as'), command=self.save_lrc_as)
        file_menu.add_separator()
        
        file_menu.add_command(label="Exit", accelerator=get_hk_string('exit'), command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        
        # Edit operations
        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Sync from Scratch", accelerator=get_hk_string('sync_mode'), command=self.toggle_sync_mode)
        edit_menu.add_separator()
        edit_menu.add_command(label="Audio Metadata", command=self.open_metadata)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        
        # Help & Settings operations
        menubar.add_command(label="Appearance", command=self.open_appearance)
        menubar.add_command(label="Settings", command=self.open_settings)
        
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Hotkeys", command=self.open_hotkeys)
        help_menu.add_command(label="Hidden Gimmicks", command=self.open_hidden_gimmicks)
        help_menu.add_command(label="About", command=self.open_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        
        self.root.config(menu=menubar)

    def toggle_loop(self):
        """Toggles looping playback state."""
        self.loop_track = not getattr(self, 'loop_track', False)
        bg_col, fg_col, box_col, track_col = get_colors(self.settings["theme"])
        self.btn_loop.config(
            text="LOOP: ON" if self.loop_track else "LOOP: OFF", 
            fg="#42f542" if self.loop_track else fg_col
        )

    def setup_ui(self):
        """Generates all core UI components of the main application layout."""
        self.top_area = tk.Frame(self.root)
        self.top_area.pack(fill="x", padx=20, pady=10)
        
        # Cover Art Frame
        self.art_frame = tk.Frame(self.top_area)
        self.art_frame.pack(side="left", padx=(0, 20))
        self.art_label = tk.Label(self.art_frame, bd=0, cursor="hand2")
        self.art_label.pack(expand=True, fill="both")
        self.art_label.bind("<Double-Button-1>", lambda e: self.save_thumbnail())
        self.art_label.bind("<Control-Button-1>", self.open_full_image)
        
        # Information Panel
        self.right_top_area = tk.Frame(self.top_area)
        self.right_top_area.pack(side="left", fill="both", expand=True)
        self.info_panel = tk.Frame(self.right_top_area)
        self.info_panel.pack(fill="x", expand=True, anchor="n")
        
        self.fn_f = tk.Frame(self.info_panel)
        self.fn_f.pack(fill="x")
        self.audio_name_lab = tk.Label(self.fn_f, text="File Name: None", font=("Segoe UI", 12, "bold"), cursor="hand2")
        self.audio_name_lab.pack(side="left")
        self.audio_name_lab.bind("<Double-Button-1>", lambda e: self.copy_txt(self.audio_path, self.audio_name_lab, "File Name: "))
        self.audio_name_lab.bind("<Control-Button-1>", self.open_metadata)
        
        self.edited_lbl = tk.Label(self.fn_f, text="(edited)", font=("Segoe UI", 10, "italic"), fg="#ff4444")
        
        self.audio_path_lab = tk.Label(self.info_panel, text="Path: None", font=("Segoe UI", 8), cursor="hand2")
        self.audio_path_lab.pack(anchor="w", pady=(0, 10))
        self.audio_path_lab.bind("<Double-Button-1>", lambda e: self.copy_dir(self.audio_path, self.audio_path_lab, "Path: "))
        
        self.lrc_name_lab = tk.Label(self.info_panel, text="LRC File: None", font=("Segoe UI", 10, "bold"), cursor="hand2")
        self.lrc_name_lab.pack(anchor="w")
        self.lrc_name_lab.bind("<Double-Button-1>", lambda e: self.copy_txt(self.lrc_path, self.lrc_name_lab, "LRC File: "))
        
        self.lrc_path_lab = tk.Label(self.info_panel, text="Path: None", font=("Segoe UI", 8), cursor="hand2")
        self.lrc_path_lab.pack(anchor="w", pady=(0, 5))
        self.lrc_path_lab.bind("<Double-Button-1>", lambda e: self.copy_dir(self.lrc_path, self.lrc_path_lab, "Path: "))
        
        self.tech_info_lab = tk.Label(self.info_panel, text="Size: - | Bitrate: -", font=("Segoe UI", 8, "bold"))
        self.tech_info_lab.pack(anchor="w")
        
        # Source Selection (File vs Meta)
        self.src_f = tk.Frame(self.info_panel)
        self.src_f.pack(anchor="w", pady=5)
        self.src_var = tk.StringVar(value="file")
        self.rb1 = tk.Radiobutton(self.src_f, text="LRC File", variable=self.src_var, value="file", command=self.refresh_views)
        self.rb1.pack(side="left")
        self.rb2 = tk.Radiobutton(self.src_f, text="Metadata", variable=self.src_var, value="meta", command=self.refresh_views)
        self.rb2.pack(side="left")
        
        # Timer Frame
        self.timer_frame = tk.Frame(self.right_top_area)
        self.timer_frame.pack(fill="x", side="bottom")
        self.timer_msg = tk.Label(self.timer_frame, text="", font=("Consolas", 10, "bold"), fg="#42f542")
        self.timer_msg.pack(side="top", anchor="e", padx=10)
        self.time_label = tk.Label(self.timer_frame, text="00:00.00 / 00:00.00", font=("Consolas", 24, "bold"), cursor="hand2")
        self.time_label.pack(side="top", anchor="e")
        self.time_label.bind("<Double-Button-1>", lambda e: self.copy_timer())
        
        # Seek Canvas (Progress Bar)
        self.seek_canvas = tk.Canvas(self.root, height=28, bd=0, highlightthickness=0, cursor="hand2")
        self.seek_canvas.pack(fill="x", padx=20, pady=2)
        self.seek_canvas.bind("<Button-1>", self.on_seek)
        self.seek_canvas.bind("<B1-Motion>", self.on_seek)
        self.seek_canvas.bind("<ButtonRelease-1>", self.on_seek_release)
        
        # Bottom Controls
        self.ctrl = tk.Frame(self.root)
        self.ctrl.pack(fill="x", padx=20, pady=5)
        
        self.sign_btn = tk.Button(self.ctrl, text=self.settings["offset_sign"], width=4, font="bold", command=self.toggle_sign)
        self.sign_btn.pack(side="left")
        
        self.off_m = tk.Spinbox(self.ctrl, from_=0, to=99, width=3, textvariable=self.off_m_var, command=self.apply_offset)
        self.off_m.pack(side="left", padx=2)
        tk.Label(self.ctrl, text="m").pack(side="left")
        
        self.off_s = tk.Spinbox(self.ctrl, from_=0, to=59, width=3, textvariable=self.off_s_var, command=self.apply_offset)
        self.off_s.pack(side="left", padx=2)
        tk.Label(self.ctrl, text="s").pack(side="left")
        
        self.off_ms = tk.Spinbox(self.ctrl, from_=0, to=9, width=3, textvariable=self.off_ms_var, command=self.apply_offset)
        self.off_ms.pack(side="left", padx=2)
        tk.Label(self.ctrl, text="ms").pack(side="left")
        
        tk.Button(self.ctrl, text="RESET", command=self.reset_offset).pack(side="left", padx=10)
        
        # Search Section
        self.search_frame = tk.Frame(self.ctrl)
        tk.Label(self.search_frame, text="Find:", font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0,5))
        self.search_entry = tk.Entry(self.search_frame, font=("Segoe UI", 11), width=25)
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.insert(0, self.settings.get("last_search", ""))
        
        self.nav_f = tk.Frame(self.search_frame)
        self.nav_f.pack(side="left", padx=2)
        self.btn_s_up = tk.Button(self.nav_f, text="↑", width=3, command=self.search_prev)
        self.btn_s_up.pack(side="left")
        self.btn_s_dn = tk.Button(self.nav_f, text="↓", width=3, command=self.search_next)
        self.btn_s_dn.pack(side="left")
        
        self.search_info_lbl = tk.Label(self.search_frame, text="", font=("Segoe UI", 9, "bold"), width=12)
        self.search_info_lbl.pack(side="left", padx=5)
        tk.Button(self.search_frame, text="X", font=("Segoe UI", 8, "bold"), fg="#ff4444", command=self.toggle_search).pack(side="left", padx=5)
        
        self.search_entry.bind("<Return>", lambda e: self.search_next())
        self.search_entry.bind("<Up>", lambda e: self.search_prev())
        self.search_entry.bind("<Down>", lambda e: self.search_next())
        
        # Playback Controls
        self.btn_play = tk.Button(self.ctrl, text="PLAY", width=12, command=self.toggle_playback, font=("Segoe UI", 10, "bold"))
        self.btn_play.pack(side="right")
        self.btn_loop = tk.Button(self.ctrl, text="LOOP: OFF", width=10, command=self.toggle_loop, font=("Segoe UI", 10, "bold"))
        self.btn_loop.pack(side="right", padx=(0, 5))
        
        self.vol_scale = tk.Scale(self.ctrl, from_=0, to=100, orient="horizontal", showvalue=False, bd=0, highlightthickness=0, command=self.change_vol)
        self.vol_scale.set(self.settings.get("volume", 75))
        self.vol_scale.pack(side="right", padx=15)
        self.vol_lbl = tk.Label(self.ctrl, text="Volume")
        self.vol_lbl.pack(side="right")
        
        # Work Area Boxes
        self.work_area = tk.Frame(self.root, bg="#050505")
        self.work_area.pack(fill="both", expand=True, padx=20, pady=10)
        self.box_container = tk.Frame(self.work_area, bg="#050505")
        self.box_container.pack(fill="both", expand=True)
        
        self.left_col = self.setup_box(self.box_container, "ORIGINAL", True, self.auto_scroll_orig, 50)
        self.right_col = self.setup_box(self.box_container, "SHIFTED", False, self.auto_scroll_shft, 115)
        
        self.left_col["txt"].bind("<Triple-Button-3>", lambda e: [self.left_col["txt"].delete("1.0", tk.END), self.apply_offset()])
        self.right_col["txt"].bind("<Triple-Button-3>", lambda e: [self.left_col["txt"].delete("1.0", tk.END), self.apply_offset()])
        
        self.btn_sort = tk.Button(self.right_col["t_f"], text="SORT LYRICS", font=("Segoe UI", 8, "bold"), bg="#ff4444", fg="white", command=self.sort_lyrics)
        self.btn_restore_orig = tk.Button(self.left_col["t_f"], text="RESTORE ORIGINAL", font=("Segoe UI", 8, "bold"), bg="#ffaa00", fg="black", command=self.restore_original_text)

        # Sync from Scratch Box
        self.sync_col = self.setup_box(self.box_container, "SYNC FROM SCRATCH", False, tk.BooleanVar(value=True), 125)
        self.sync_col["frame"].pack_forget()
        
        # Re-build top frame of sync box
        for w in self.sync_col["t_f"].winfo_children(): 
            w.destroy()
            
        tk.Label(self.sync_col["t_f"], text="SYNC FROM SCRATCH", font=("Segoe UI", 9, "bold"), bg="#050505", fg="#00ffc3").pack(side="left")
        tk.Label(self.sync_col["t_f"], text="Sync Offset (ms):", font=("Segoe UI", 8), bg="#050505", fg="white").pack(side="left", padx=(15, 2))
        
        self.sync_off_var = tk.StringVar(value=str(self.settings.get("sync_offset", 0)))
        self.sync_off_var.trace("w", lambda *a: self.settings.update({"sync_offset": int(self.sync_off_var.get() or 0) if self.sync_off_var.get() not in ["", "-"] else 0}) or self.save_settings())
        
        self.sync_off_sp = tk.Spinbox(self.sync_col["t_f"], from_=-100, to=0, increment=10, width=5, textvariable=self.sync_off_var)
        self.sync_off_sp.pack(side="left")
        
        btn_exit_sync = tk.Button(self.sync_col["t_f"], text="SAVE & EXIT", font=("Segoe UI", 8, "bold"), bg="#42f542", fg="black", command=lambda: self.exit_sync_mode(save=True))
        btn_exit_sync.custom_tag = "exit_sync"
        btn_exit_sync.pack(side="right", padx=10)
        
        btn_cancel_sync = tk.Button(self.sync_col["t_f"], text="CANCEL", font=("Segoe UI", 8, "bold"), bg="#ff4444", fg="white", command=lambda: self.exit_sync_mode(save=False))
        btn_cancel_sync.custom_tag = "exit_sync"
        btn_cancel_sync.pack(side="right", padx=5)
        
        self.auto_scroll_sync = tk.BooleanVar(value=True)
        tk.Checkbutton(
            self.sync_col["t_f"], 
            text="Auto-scroll", 
            variable=self.auto_scroll_sync, 
            font=("Segoe UI", 8), 
            bg="#050505", 
            selectcolor="#050505", 
            activebackground="#050505"
        ).pack(side="right", padx=5)
        
        self.sync_col["txt"].bind("<Double-Button-1>", lambda e: self.seek_to_line(e, self.sync_col["txt"], "SYNC"))

    # =========================================================================
    # NAVIGATION AND TIMING OPERATIONS
    # =========================================================================

    def _nav_seek(self, d):
        """Moves line focus and jumps to that time in the player."""
        if isinstance(self.root.focus_get(), (tk.Entry, tk.Spinbox)): 
            return "break"
        if getattr(self, 'in_sync_mode', False):
            self.nav_sync_line(d, seek=True)
            return "break"
        else:
            if d < 0 and self.shft_ts and self.last_act_shft > 0:
                t = self.shft_ts[max(0, self.last_act_shft - 1)][0]
                if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped]:
                    self.player.play()
                    self.player.set_pause(1)
                self.player.set_time(int(t * 1000))
                self.last_drawn_curr = -1
                self.update_loop_logic()
            elif d > 0 and self.shft_ts and self.last_act_shft >= 0 and self.last_act_shft < len(self.shft_ts) - 1:
                t = self.shft_ts[min(len(self.shft_ts)-1, self.last_act_shft + 1)][0]
                if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped]:
                    self.player.play()
                    self.player.set_pause(1)
                self.player.set_time(int(t * 1000))
                self.last_drawn_curr = -1
                self.update_loop_logic()
        return "break"

    def _nav_noseek(self, d):
        """Moves line focus without jumping time."""
        if getattr(self, 'in_sync_mode', False):
            self.nav_sync_line(d, seek=False)
            return "break"

    def _nav_up(self):
        """Navigates up safely without jumping time, specific for arrow keys."""
        if isinstance(self.root.focus_get(), (tk.Entry, tk.Spinbox)): 
            return "break"
        if getattr(self, 'in_sync_mode', False):
            self.nav_sync_line(-1, seek=False)
        else:
            if self.shft_ts and self.last_act_shft > 0:
                t = self.shft_ts[max(0, self.last_act_shft - 1)][0]
                if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped]:
                    self.player.play()
                    self.player.set_pause(1)
                self.player.set_time(int(t * 1000))
                self.last_drawn_curr = -1
                self.update_loop_logic()
        return "break"

    def _nav_down(self):
        """Navigates down safely without jumping time, specific for arrow keys."""
        if isinstance(self.root.focus_get(), (tk.Entry, tk.Spinbox)): 
            return "break"
        if getattr(self, 'in_sync_mode', False):
            self.nav_sync_line(1, seek=False)
        else:
            if self.shft_ts and self.last_act_shft >= 0 and self.last_act_shft < len(self.shft_ts) - 1:
                t = self.shft_ts[min(len(self.shft_ts)-1, self.last_act_shft + 1)][0]
                if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped]:
                    self.player.play()
                    self.player.set_pause(1)
                self.player.set_time(int(t * 1000))
                self.last_drawn_curr = -1
                self.update_loop_logic()
        return "break"

    def nav_sync_line(self, direction, seek=True):
        """Iterates through lines in sync mode looking for valid text strings."""
        lines = self.sync_col["txt"].get("1.0", "end-1c").split('\n')
        idx = self.sync_current_line + direction
        
        while 0 <= idx < len(lines):
            if LRC_REGEX.sub("", lines[idx]).strip():
                self.sync_current_line = idx
                self.highlight_sync_line()
                if seek:
                    m = LRC_REGEX.search(lines[idx])
                    if m and self.player:
                        mn, sc, d = m.groups()
                        t = int(mn)*60 + int(sc) + float(f"0.{d}")
                        if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped]:
                            self.player.play()
                            self.player.set_pause(1)
                        self.player.set_time(int(t * 1000))
                        self.last_drawn_curr = -1
                        self.update_loop_logic()
                break
            idx += direction

    def _global_space(self, e):
        """Handles spacebar logic (playback vs stamp)."""
        if isinstance(e.widget, (tk.Entry, tk.Spinbox)): 
            return
        if getattr(self, 'in_sync_mode', False):
            self.stamp_sync()
            return "break"
        else:
            self.toggle_playback()
            return "break"
            
    def _global_enter(self, e):
        """Handles the Enter key."""
        if isinstance(e.widget, (tk.Entry, tk.Spinbox)): 
            return
        self.stamp_sync()
        return "break"

    def on_escape(self, e):
        """Closes all pop-ups or cancels sync mode safely."""
        closed_any = False
        for win in list(self.open_windows.values()):
            if win.winfo_exists(): 
                win.destroy()
                closed_any = True
                
        self.open_windows.clear()
        self.sub_windows.clear()
        
        if self.search_frame.winfo_viewable():
            self.toggle_search()
            closed_any = True
            
        if getattr(self, 'in_sync_mode', False) and not closed_any:
            self.exit_sync_mode(save=False)

    def toggle_sync_mode(self, e=None):
        """Enters the immersive Sync From Scratch mode."""
        if not getattr(self, 'in_sync_mode', False):
            self.in_sync_mode = True
            self.left_col["frame"].pack_forget()
            self.right_col["frame"].pack_forget()
            self.sync_col["frame"].pack(side="left", fill="both", expand=True)
            
            for w in [self.sign_btn, self.off_m, self.off_s, self.off_ms, self.btn_sort]: 
                w.config(state="disabled")
            
            raw = self.left_col["txt"].get("1.0", "end-1c")
            # Strip empty lines out completely when entering sync mode
            lines = [l for l in raw.split('\n') if LRC_REGEX.sub("", l).strip()]
            
            self.sync_col["txt"].config(state="normal")
            self.sync_col["txt"].delete("1.0", tk.END)
            self.sync_col["txt"].insert("1.0", "\n".join(lines))
            self.sync_col["txt"].config(state="disabled", padx=250)
            
            self.sync_current_line = 0
            for i, l in enumerate(lines):
                if LRC_REGEX.sub("", l).strip():
                    self.sync_current_line = i
                    break
                    
            self._refresh_sync_errors()
            self.highlight_sync_line()
            self.sync_col["txt"].focus_set()
            
            if self.search_frame.winfo_viewable(): 
                self.toggle_search()
        else:
            self.exit_sync_mode(save=True)
            
    def exit_sync_mode(self, save=True):
        """Exits Sync From Scratch mode and optionally saves results."""
        if not getattr(self, 'in_sync_mode', False): 
            return
            
        self.in_sync_mode = False
        self.sync_col["frame"].pack_forget()
        self.left_col["frame"].pack(side="left", fill="both", expand=True)
        self.right_col["frame"].pack(side="left", fill="both", expand=True)
        
        for w in [self.sign_btn, self.off_m, self.off_s, self.off_ms, self.btn_sort]: 
            w.config(state="normal")
        
        if save:
            synced = self.sync_col["txt"].get("1.0", "end-1c")
            self.left_col["txt"].config(state="normal")
            self.left_col["txt"].delete("1.0", tk.END)
            self.left_col["txt"].insert("1.0", synced)
            
            lines_count = len(synced.split('\n'))
            self.line_tracker = list(range(1, lines_count + 1))
            
        self.last_act_orig = -1
        self.last_act_shft = -1
        self.apply_offset()
        self.root.focus_set()

    def _get_time_errors_lis(self, ts_list):
        """Calculates Longest Increasing Subsequence to detect chronologically out-of-order timestamps."""
        if not ts_list: 
            return set()
            
        tails = []
        tail_indices = []
        parent = [-1] * len(ts_list)
        
        for i, (t, idx) in enumerate(ts_list):
            pos = bisect.bisect_right([x[0] for x in tails], t)
            if pos > 0: 
                parent[i] = tail_indices[pos-1]
            if pos == len(tails):
                tails.append((t, idx))
                tail_indices.append(i)
            else:
                tails[pos] = (t, idx)
                tail_indices[pos] = i
                
        lis_indices = set()
        curr = tail_indices[-1] if tail_indices else -1
        
        while curr != -1:
            lis_indices.add(curr)
            curr = parent[curr]
            
        errs = set()
        for i in range(len(ts_list)):
            if i not in lis_indices:
                errs.add(ts_list[i][1])
                
        return errs

    def _refresh_sync_errors(self):
        """Refreshes highlighting of chronological errors purely inside Sync Mode."""
        txt = self.sync_col["txt"]
        raw = txt.get("1.0", "end-1c")
        ts_data = []
        
        for i, line in enumerate(raw.split("\n")):
            if m := LRC_REGEX.search(line):
                mn, sc, d = m.groups()
                t = int(mn)*60 + int(sc) + float(f"0.{d}")
                ts_data.append((t, i))
        
        errs = self._get_time_errors_lis(ts_data)
        txt.config(state="normal")
        txt.tag_remove("time_err", "1.0", tk.END)
        
        for idx in errs:
            start = f"{idx+1}.0"
            pos = txt.search(r"\[\d{2}:\d{2}\.\d+\]", start, stopindex=f"{idx+1}.end", regexp=True)
            if pos:
                m_txt = txt.get(pos, f"{idx+1}.end")
                if m := LRC_REGEX.search(m_txt):
                    match_len = len(m.group(0))
                    txt.tag_add("time_err", pos, f"{pos}+{match_len}c")
                    
        txt.config(state="disabled")

    def stamp_sync(self, event=None):
        """Grabs current playback time and stamps it onto a specific line."""
        if not self.player: 
            return "break"
            
        curr_time = self.interpolated_time
        
        if getattr(self, 'in_sync_mode', False):
            try: 
                offset = int(self.sync_off_var.get() or 0) / 1000.0
            except Exception: 
                offset = 0.0
                
            stamp_time = max(0.0, curr_time + offset)
            nm, ns = divmod(int(stamp_time), 60)
            stamp_str = f"[{nm:02d}:{ns:02d}.{int((stamp_time*100)%100):02d}]"
            
            idx = self.sync_current_line
            txt = self.sync_col["txt"]
            lines = txt.get("1.0", "end-1c").split('\n')
            
            if idx >= len(lines): 
                return "break"
            
            line = lines[idx]
            if LRC_REGEX.match(line): 
                line = LRC_REGEX.sub(stamp_str, line, count=1)
            else: 
                line = stamp_str + " " + line
                
            txt.config(state="normal")
            txt.delete(f"{idx+1}.0", f"{idx+1}.end")
            txt.insert(f"{idx+1}.0", line)
            
            self._refresh_sync_errors()
            
            # Move to next line naturally
            next_idx = idx + 1
            while next_idx < len(lines):
                if LRC_REGEX.sub("", lines[next_idx]).strip(): 
                    break
                next_idx += 1
                
            self.sync_current_line = min(next_idx, len(lines) - 1) if next_idx < len(lines) else len(lines) - 1
            self.highlight_sync_line()
            txt.config(state="disabled")
            self.sync_col["char_lbl"].config(text=f"Characters: {len(txt.get('1.0', tk.END).strip())}")
        else:
            # Not in sync mode, use enter to stamp left column
            if self.last_act_shft != -1:
                idx = self.last_act_shft
                txt = self.left_col["txt"]
                lines = txt.get("1.0", "end-1c").split('\n')
                if idx < len(lines):
                    nm, ns = divmod(int(curr_time), 60)
                    stamp_str = f"[{nm:02d}:{ns:02d}.{int((curr_time*100)%100):02d}]"
                    line = lines[idx]
                    
                    if LRC_REGEX.match(line): 
                        line = LRC_REGEX.sub(stamp_str, line, count=1)
                    else: 
                        line = stamp_str + " " + line
                        
                    txt.config(state="normal")
                    txt.delete(f"{idx+1}.0", f"{idx+1}.end")
                    txt.insert(f"{idx+1}.0", line)
                    self.apply_offset()
        return "break"

    def highlight_sync_line(self):
        """Adds visual distinct highlight to the focused line in Sync Mode."""
        txt = self.sync_col["txt"]
        txt.tag_remove("sync_hl", "1.0", tk.END)
        idx = self.sync_current_line
        lines_count = int(txt.index("end-1c").split(".")[0])
        
        if idx < lines_count:
            txt.tag_add("sync_hl", f"{idx+1}.0", f"{idx+1}.end")
            if self.auto_scroll_sync.get():
                txt.yview_moveto(max(0, (idx - 8) / max(1, lines_count)))

    def draw_sync_gutter(self):
        """Draws the dynamic 'time until next play' counter in Sync Mode."""
        txt = self.sync_col["txt"]
        gut = self.sync_col["gut"]
        gut.delete("all")
        lines = txt.get("1.0", "end-1c").split('\n')
        curr = self.interpolated_time
        sync_bg_col = self.settings.get("sync_bg", "#ffaa00")
        
        for ln in range(int(txt.index("@0,0").split(".")[0]), int(txt.index(f"@0,{txt.winfo_height()}").split(".")[0]) + 2):
            if bbox := txt.bbox(f"{ln}.0"):
                y = bbox[1]
                gut.create_text(45, y+10, text=str(ln), fill="gray", font="Consolas 8", anchor="e")
                
                if ln - 1 == self.sync_current_line:
                    # Pointing arrow to current line
                    gut.create_polygon(55, y+5, 55, y+15, 63, y+10, fill=sync_bg_col)
                    if ln - 1 < len(lines):
                        m = LRC_REGEX.search(lines[ln-1])
                        if m:
                            mn, sc, d = m.groups()
                            t = int(mn)*60 + int(sc) + float(f"0.{d}")
                            diff = t - curr
                            if diff > 0:
                                gut.create_text(
                                    115, y+10, 
                                    text=f"in {diff:.1f}s", 
                                    fill=sync_bg_col, 
                                    font=("Consolas", 8, "bold"), 
                                    anchor="e"
                                )

    def restore_original_text(self):
        """Restores the original loaded text before any shifts were applied."""
        if hasattr(self, 'true_original_text'):
            self.left_col["txt"].delete("1.0", tk.END)
            self.left_col["txt"].insert("1.0", self.true_original_text)
            lines_count = int(self.left_col["txt"].index("end-1c").split('.')[0])
            self.line_tracker = list(range(1, lines_count + 1))
            self.local_offsets.clear()
            self.apply_offset()

    def reset_offset(self):
        """Zeroes out standard or sync offset."""
        if getattr(self, 'in_sync_mode', False):
            self.sync_off_var.set("0")
            return
            
        if self.ctx_menu and self.ctx_menu.winfo_exists():
            self.ctx_m_var.set("0")
            self.ctx_s_var.set("0")
            self.ctx_ms_var.set("0")
            self._set_sign("+")
            self._live_preview()
        else:
            self.off_m_var.set("0")
            self.off_s_var.set("0")
            self.off_ms_var.set("0")
            self._set_sign("+")
            self.apply_offset()

    def add_min(self):
        """Adds one minute, or adjusts Sync offset negatively."""
        if getattr(self, 'in_sync_mode', False):
            try:
                val = max(-100, int(self.sync_off_var.get() or 0) - 10)
                self.sync_off_var.set(str(val))
            except Exception: 
                pass
            return
            
        try:
            if self.ctx_menu and self.ctx_menu.winfo_exists():
                val = int(self.ctx_m_var.get() or 0)
                self.ctx_m_var.set(str(min(99, val + 1)))
                self._live_preview()
            else:
                val = int(self.off_m_var.get() or 0)
                self.off_m_var.set(str(min(99, val + 1)))
                self.apply_offset()
        except Exception: 
            pass

    def add_sec(self):
        """Adds one second, or adjusts Sync offset negatively."""
        if getattr(self, 'in_sync_mode', False):
            try:
                val = max(-100, int(self.sync_off_var.get() or 0) - 10)
                self.sync_off_var.set(str(val))
            except Exception: 
                pass
            return
            
        try:
            if self.ctx_menu and self.ctx_menu.winfo_exists():
                val = int(self.ctx_s_var.get() or 0)
                if val >= 59: 
                    self.ctx_s_var.set("0")
                    self.add_min()
                else: 
                    self.ctx_s_var.set(str(val + 1))
                    self._live_preview()
            else:
                val = int(self.off_s_var.get() or 0)
                if val >= 59: 
                    self.off_s_var.set("0")
                    self.add_min()
                else: 
                    self.off_s_var.set(str(val + 1))
                    self.apply_offset()
        except Exception: 
            pass

    def add_ms(self):
        """Adds ten ms, or adjusts Sync offset negatively."""
        if getattr(self, 'in_sync_mode', False):
            try:
                val = max(-100, int(self.sync_off_var.get() or 0) - 10)
                self.sync_off_var.set(str(val))
            except Exception: 
                pass
            return
            
        try:
            if self.ctx_menu and self.ctx_menu.winfo_exists():
                val = int(self.ctx_ms_var.get() or 0)
                if val >= 9: 
                    self.ctx_ms_var.set("0")
                    self.add_sec()
                else: 
                    self.ctx_ms_var.set(str(val + 1))
                    self._live_preview()
            else:
                val = int(self.off_ms_var.get() or 0)
                if val >= 9: 
                    self.off_ms_var.set("0")
                    self.add_sec()
                else: 
                    self.off_ms_var.set(str(val + 1))
                    self.apply_offset()
        except Exception: 
            pass

    def setup_box(self, p, t, ed, s_v, gut_w):
        """Helper to create a standard text/gut column structure."""
        f = tk.Frame(p, bg="#050505")
        f.pack(side="left", fill="both", expand=True, padx=0)
        
        t_f = tk.Frame(f, bg="#050505")
        t_f.pack(fill="x")
        tk.Label(t_f, text=t, font=("Segoe UI", 9, "bold"), bg="#050505").pack(side="left")
        tk.Checkbutton(t_f, text="Auto-scroll", variable=s_v, font=("Segoe UI", 8), bg="#050505").pack(side="right")
        
        c = tk.Frame(f, bg="#050505")
        c.pack(fill="both", expand=True)
        
        g = tk.Canvas(c, width=gut_w, bd=0, highlightthickness=0, bg="#050505")
        g.pack(side="left", fill="y")
        
        txt = tk.Text(c, font=("Consolas", 12), undo=True, wrap="none", bd=0, bg="#222222", fg="#e0e0e0", cursor="xterm" if ed else "arrow")
        txt.pack(side="left", fill="both", expand=True)
        
        sb = ttk.Scrollbar(c, orient="vertical", command=txt.yview)
        sb.pack(side="right", fill="y")
        txt.configure(yscrollcommand=sb.set)
        
        ch_lbl = tk.Label(f, text="Characters: 0", font=("Segoe UI", 8, "italic"), bg="#050505")
        ch_lbl.pack(anchor="w", pady=(2,0))
        
        if ed: 
            txt.config(state="normal")
            txt.bind("<KeyRelease>", self.on_text_keyrelease)
            def on_paste(e, w=txt):
                try:
                    clip = w.clipboard_get().replace("\r\n", "\n").replace("\r", "\n")
                    w.insert(tk.INSERT, clip)
                    self.apply_offset()
                except Exception: 
                    pass
                return "break"
            txt.bind("<<Paste>>", on_paste)
        else: 
            txt.config(state="disabled")
            
        txt.bind("<Double-Button-1>", lambda e, w=txt, col=t: self.seek_to_line(e, w, col))
        txt.bind("<Control-MouseWheel>", self.on_global_scroll)
        txt.bind("<MouseWheel>", self.on_text_scroll)
        txt.bind("<Shift-MouseWheel>", self.on_shift_scroll)
        txt.bind("<FocusIn>", lambda e: self.clear_search_highlight())
        txt.bind("<Button-3>", lambda e, w=txt, col=t: self.show_context_menu(e, w, col))
        
        return {"txt": txt, "gut": g, "frame": f, "t_f": t_f, "char_lbl": ch_lbl}

    def on_text_keyrelease(self, e):
        """Triggered upon key release in editable mode."""
        if e.keysym in ["Alt_L", "Alt_R", "Control_L", "Control_R", "Shift_L", "Shift_R"]: 
            return
        self.apply_offset()

    def close_ctx_menu(self, cancel=False):
        """Destroys context popups."""
        if self.ctx_menu and self.ctx_menu.winfo_exists():
            if cancel: 
                self.temp_local_offsets.clear()
                self.apply_offset()
            self.ctx_menu.destroy()
            self.ctx_menu = None
            self.ctx_sign_btn = None
            self.bind_all_hotkeys()

    def show_context_menu(self, e, txt_widget, col_type):
        """Displays right-click context menu options."""
        if getattr(self, 'in_sync_mode', False): 
            return
            
        self.close_ctx_menu(cancel=True)
        try: 
            sl = int(txt_widget.index(tk.SEL_FIRST).split('.')[0]) - 1
            el = int(txt_widget.index(tk.SEL_LAST).split('.')[0]) - 1
        except tk.TclError: 
            sl = el = int(txt_widget.index(f"@{e.x},{e.y}").split('.')[0]) - 1
            
        self.ctx_sel_range = (sl, el)
        self.temp_local_offsets = self.local_offsets.copy()
        
        bg_col, fg_col, box_col, track_col = get_colors(self.settings["theme"])
        self.ctx_menu = tk.Toplevel(self.root)
        self.ctx_menu.overrideredirect(True)
        self.ctx_menu.config(bg=bg_col, bd=2, relief="solid")
        
        def btn(t, cmd, c_fg=fg_col): 
            tk.Button(self.ctx_menu, text=t, font=("Segoe UI", 9), bg=bg_col, fg=c_fg, activebackground=box_col, bd=0, anchor="w", padx=10, command=lambda: [cmd(), self.close_ctx_menu()]).pack(fill="x")
            
        btn("Copy", lambda: txt_widget.event_generate("<<Copy>>"))
        
        if col_type == "ORIGINAL": 
            btn("Paste", lambda: [txt_widget.event_generate("<<Paste>>"), self.apply_offset()])
            btn("Delete", lambda: [txt_widget.event_generate("<<Clear>>"), self.apply_offset()])
            btn("Clear All", lambda: [txt_widget.delete("1.0", tk.END), self.apply_offset()])
            
        tk.Frame(self.ctx_menu, height=1, bg=box_col).pack(fill="x", pady=2)
        
        if col_type == "SHIFTED":
            def reset_lo():
                for i in range(sl, el + 1):
                    self.local_offsets.pop(i, None)
                self.apply_offset()
            btn("Reset Local Offset", reset_lo, c_fg="#ffaa00")
            tk.Frame(self.ctx_menu, height=1, bg=box_col).pack(fill="x", pady=2)
            
        def do_srch():
            try:
                sel = txt_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
                self.search_entry.delete(0, tk.END)
                self.search_entry.insert(0, sel)
                if not self.search_frame.winfo_viewable(): 
                    self.toggle_search()
                self.run_search()
            except tk.TclError: 
                pass
                
        btn("Search Selection", do_srch)
        tk.Frame(self.ctx_menu, height=1, bg=box_col).pack(fill="x", pady=2)
        
        tk.Label(self.ctx_menu, text=f"Local Offset (Lines {sl+1}-{el+1})", font=("Segoe UI", 8, "bold"), bg=bg_col, fg=self.settings["active_bg"]).pack(pady=(2,5))
        of_f = tk.Frame(self.ctx_menu, bg=bg_col)
        of_f.pack(padx=5, pady=2)
        
        self.ctx_sign_btn = tk.Button(of_f, textvariable=self.ctx_sign, width=2, font="bold", bg="#44ff44" if self.ctx_sign.get()=="+" else "#ff4444", fg="black", bd=0, command=self.toggle_sign)
        self.ctx_sign_btn.pack(side="left", padx=2)
        
        def _d(v, m): 
            v.set(str(max(0, int(v.get() or 0)-1)))
            self._live_preview()
            
        for v, m, l, cmd_u in [(self.ctx_m_var, 99, "m", self.add_min), (self.ctx_s_var, 59, "s", self.add_sec), (self.ctx_ms_var, 9, "ms", self.add_ms)]:
            tk.Label(of_f, textvariable=v, font=("Consolas", 10, "bold"), bg=box_col, fg=fg_col, width=2).pack(side="left")
            tk.Button(of_f, text="▲", font=("Segoe UI", 6), bg=box_col, fg=fg_col, bd=0, command=cmd_u).pack(side="left")
            tk.Button(of_f, text="▼", font=("Segoe UI", 6), bg=box_col, fg=fg_col, bd=0, command=lambda vr=v, mx=m: _d(vr, mx)).pack(side="left")
            tk.Label(of_f, text=l, bg=bg_col, fg=fg_col).pack(side="left", padx=(0,2))
            
        btn_f = tk.Frame(self.ctx_menu, bg=bg_col)
        btn_f.pack(pady=5, fill="x")
        
        tk.Button(btn_f, text="Cancel", font=("Segoe UI", 8), bg=box_col, fg=fg_col, bd=0, command=lambda: self.close_ctx_menu(cancel=True)).pack(side="left", expand=True, fill="x", padx=2)
        
        def apply_lo():
            self.local_offsets = self.temp_local_offsets.copy()
            self.ctx_m_var.set("0")
            self.ctx_s_var.set("0")
            self.ctx_ms_var.set("0")
            self.ctx_sign.set("+")
            self.close_ctx_menu()
            
        tk.Button(btn_f, text="Apply", font=("Segoe UI", 8, "bold"), bg="#42f542", fg="black", bd=0, command=apply_lo).pack(side="right", expand=True, fill="x", padx=2)
        
        def ctx_wheel(e):
            if not self.player: 
                return
            self.seek_relative(0.5 if e.delta < 0 else -0.5)
            
        self.ctx_menu.bind("<MouseWheel>", ctx_wheel)
        self.ctx_menu.bind("<Control-MouseWheel>", lambda e: self.seek_relative(0.1 if e.delta > 0 else -0.1))
        self.ctx_menu.bind("<Shift-MouseWheel>", lambda e: self.on_shift_scroll(e))
        
        self.ctx_menu.update_idletasks()
        width = self.ctx_menu.winfo_reqwidth()
        height = self.ctx_menu.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x, y = e.x_root, e.y_root
        
        if x + width > sw: 
            x = sw - width
        if y + height > sh: 
            y = y - height
            
        self.ctx_menu.geometry(f"+{x}+{y}")

    def _live_preview(self):
        """Displays temporary offset changes in UI."""
        off = int(self.ctx_m_var.get() or 0)*60 + int(self.ctx_s_var.get() or 0) + int(self.ctx_ms_var.get() or 0)/10.0
        if self.ctx_sign.get() == "-": 
            off = -off
            
        self.temp_local_offsets = self.local_offsets.copy()
        
        for i in range(self.ctx_sel_range[0], self.ctx_sel_range[1] + 1):
            if off == 0: 
                self.temp_local_offsets.pop(i, None)
            else: 
                self.temp_local_offsets[i] = self.local_offsets.get(i, 0.0) + off
                
        self.apply_offset(preview_local=self.temp_local_offsets)

    def sort_lyrics(self):
        """Sorts all lyrics natively by chronological flow to repair bad imports."""
        res = messagebox.askyesnocancel("Sort Lyrics", "Chronological errors detected.\nDo you want to reorder lyrics chronologically?\n\nYES = Bake Global + Local offsets\nNO = Bake ONLY Local offsets\nCANCEL = Abort")
        if res is None: 
            return
            
        lines = self.left_col["txt"].get("1.0", "end-1c").split('\n')
        off_g = int(self.off_m_var.get() or 0)*60 + int(self.off_s_var.get() or 0) + int(self.off_ms_var.get() or 0)/10.0
        
        if self.settings["offset_sign"] == "-": 
            off_g = -off_g
        
        timed_lines = []
        untimed_dict = {}
        
        for i, line in enumerate(lines):
            orig_i = self.line_tracker[i] if i < len(self.line_tracker) else i + 1
            m = LRC_REGEX.search(line)
            if m:
                mn, sc, d = m.groups()
                t_o = int(mn)*60 + int(sc) + float(f"0.{d}")
                lo = self.local_offsets.get(i, 0.0)
                timed_lines.append((max(0, t_o + lo + (off_g if res else 0.0)), line, orig_i))
            else:
                untimed_dict[i] = (line, orig_i)
                
        timed_lines.sort(key=lambda x: x[0])
        out = []
        new_tracker = []
        timed_idx = 0
        
        for i in range(len(lines)):
            if i in untimed_dict:
                out.append(untimed_dict[i][0])
                new_tracker.append(untimed_dict[i][1])
            else:
                t, orig, o_idx = timed_lines[timed_idx]
                nm, ns = divmod(int(t), 60)
                out.append(LRC_REGEX.sub(f"[{nm:02d}:{ns:02d}.{int((t*10)%10)}]", orig))
                new_tracker.append(o_idx)
                timed_idx += 1
                
        self.line_tracker = new_tracker
        self.left_col["txt"].config(state="normal")
        self.left_col["txt"].delete("1.0", tk.END)
        self.left_col["txt"].insert("1.0", "\n".join(out))
        self.local_offsets.clear()
        
        if res: 
            self.reset_offset()
        else: 
            self.apply_offset()

    def clear_search_highlight(self):
        """Removes all yellow inline search highlights."""
        for col in [self.left_col["txt"], self.right_col["txt"]]: 
            col.tag_remove("search_all", "1.0", tk.END)
            col.tag_remove("search_cur", "1.0", tk.END)
        self.search_info_lbl.config(text="")

    def run_search(self):
        """Locates specific text substrings globally inside text boxes."""
        term = self.search_entry.get()
        self.settings["last_search"] = term
        self.save_settings()
        self.clear_search_highlight()
        
        if not term.strip(): 
            return
        
        self.search_results = []
        term_len = len(term)
        lines_count = int(self.left_col["txt"].index("end-1c").split('.')[0])
        
        for i in range(1, lines_count + 1):
            l_start = f"{i}.0"
            l_matches = []
            while True:
                pos = self.left_col["txt"].search(term, l_start, stopindex=f"{i}.end", nocase=True)
                if not pos: break
                l_matches.append(pos)
                self.left_col["txt"].tag_add("search_all", pos, f"{pos}+{term_len}c")
                l_start = f"{pos}+{term_len}c"
                
            r_start = f"{i}.0"
            r_matches = []
            while True:
                pos = self.right_col["txt"].search(term, r_start, stopindex=f"{i}.end", nocase=True)
                if not pos: break
                r_matches.append(pos)
                self.right_col["txt"].tag_add("search_all", pos, f"{pos}+{term_len}c")
                r_start = f"{pos}+{term_len}c"
                
            max_len = max(len(l_matches), len(r_matches))
            for j in range(max_len):
                l_pos = l_matches[j] if j < len(l_matches) else None
                r_pos = r_matches[j] if j < len(r_matches) else None
                self.search_results.append({
                    "line": i,
                    "l_start": l_pos,
                    "r_start": r_pos
                })
                    
        if not self.search_results:
            self.search_info_lbl.config(text="No Results")
            self.current_search_idx = -1
            return
            
        self.current_search_idx = 0
        self.highlight_current_search()

    def highlight_current_search(self):
        """Highlights the active search target in a distinct color."""
        for c in [self.left_col["txt"], self.right_col["txt"]]:
            c.tag_remove("search_cur", "1.0", tk.END)
            
        if not self.search_results: 
            return
            
        res = self.search_results[self.current_search_idx]
        term_len = len(self.search_entry.get())
        
        if res["l_start"]:
            self.left_col["txt"].tag_add("search_cur", res["l_start"], f"{res['l_start']}+{term_len}c")
            self.left_col["txt"].see(res["l_start"])
        else:
            self.left_col["txt"].see(f"{res['line']}.0")
            
        if res["r_start"]:
            self.right_col["txt"].tag_add("search_cur", res["r_start"], f"{res['r_start']}+{term_len}c")
            self.right_col["txt"].see(res["r_start"])
        else:
            self.right_col["txt"].see(f"{res['line']}.0")
            
        self.search_info_lbl.config(text=f"{self.current_search_idx + 1}/{len(self.search_results)}")

    def search_next(self):
        """Advances pointer to the next search occurrence."""
        if not self.search_results or self.search_entry.get() != self.settings.get("last_search", ""):
            return self.run_search()
        self.current_search_idx = (self.current_search_idx + 1) % len(self.search_results)
        self.highlight_current_search()

    def search_prev(self):
        """Moves pointer to the previous search occurrence."""
        if not self.search_results or self.search_entry.get() != self.settings.get("last_search", ""):
            return self.run_search()
        self.current_search_idx = (self.current_search_idx - 1) % len(self.search_results)
        self.highlight_current_search()

    def save_thumbnail(self):
        """Exports currently tracked APIC frame byte data to local computer."""
        if not self.current_art_data: 
            return
        init_dir = os.path.dirname(self.audio_path) if self.audio_path else APP_DIR
        p = filedialog.asksaveasfilename(initialdir=init_dir, defaultextension=".jpg", filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png"), ("All Files", "*.*")])
        if p:
            try: 
                with open(p, "wb") as f:
                    f.write(self.current_art_data)
                messagebox.showinfo("Saved", "Thumbnail saved successfully.")
            except Exception: 
                pass

    def open_full_image(self, e=None):
        """Expands image payload using OS native viewer."""
        if not self.current_art_data: 
            return
        try:
            temp_path = os.path.join(tempfile.gettempdir(), "lrc_shifter_art_temp.jpg")
            with open(temp_path, "wb") as f:
                f.write(self.current_art_data)
            if os.name == 'nt':
                os.startfile(temp_path) 
            else:
                subprocess.call(["xdg-open", temp_path])
        except Exception: 
            pass

    def import_lrc_from_audio(self, e=None):
        """Pulls USLT or SYLT tag structures natively injected in MP3/FLACs."""
        args = {"filetypes": [("Audio", "*.mp3 *.flac *.wav *.m4a")]}
        if not self.audio_path: 
            args["initialdir"] = self._get_init_dir()
        
        if path := filedialog.askopenfilename(**args):
            lyrics = self._get_meta_lyrics(path)
            if lyrics:
                if getattr(self, 'in_sync_mode', False): 
                    self.exit_sync_mode(save=False)
                self.lrc_path = ""
                self.lrc_name_lab.config(text=f"Imported from: {os.path.basename(path)}")
                self.lrc_path_lab.config(text=f"Path: {os.path.dirname(path)}")
                self.lrc_from_file = lyrics
                self.src_var.set("file")
                self.refresh_views()
                messagebox.showinfo("Success", "Lyrics successfully imported from audio file.")
            else:
                messagebox.showwarning("No Lyrics", "No lyrics found in the selected audio file.")

    def _set_sign(self, s):
        """Sets plus or minus orientation for shift engine."""
        if getattr(self, 'in_sync_mode', False): 
            return
        if self.ctx_menu and self.ctx_menu.winfo_exists():
            self.ctx_sign.set(s)
            if self.ctx_sign_btn: 
                self.ctx_sign_btn.config(bg="#44ff44" if s=="+" else "#ff4444")
            self._live_preview()
        else:
            self.settings["offset_sign"] = s
            self.sign_btn.config(text=s, bg="#44ff44" if s=="+" else "#ff4444")
            self.apply_offset()

    def toggle_sign(self):
        """Inverts shift calculation parameters."""
        if getattr(self, 'in_sync_mode', False): 
            return
        if self.ctx_menu and self.ctx_menu.winfo_exists():
            self._set_sign("-" if self.ctx_sign.get() == "+" else "+")
        else:
            self._set_sign("-" if self.settings["offset_sign"] == "+" else "+")
            
    def change_vol(self, val):
        if self.player: 
            self.player.audio_set_volume(int(val))
        self.settings["volume"] = int(val)
        self.save_settings()

    def update_thumb_size(self, val): 
        self.settings["thumb_size"] = int(val)
        self.save_settings()
        self.refresh_thumbnail()

    def on_text_scroll(self, e):
        """Standard wheel scroll action mapping."""
        if e.state & 0x0001: 
            return self.on_shift_scroll(e)
        if e.state & 0x0004: 
            return self.on_global_scroll(e)
        e.widget.yview_scroll(int(-1*(e.delta/120)), "units")
        return "break"

    def on_global_scroll(self, e):
        """General shift mapping allowing standard 1s timeline jumps."""
        if e.state & 0x0001: 
            return self.on_shift_scroll(e)
        if not self.player: 
            return
            
        direction = 1 if e.delta < 0 else -1
        if self.settings.get("inv_scroll_time", False): 
            direction *= -1
            
        multiplier = 0.1 if (e.state & 0x0004) else 1.0
        self.seek_relative(direction * multiplier)
        return "break"

    def on_shift_scroll(self, e):
        """Shift-scroll dynamically tracks nearest timeline element to hop segments."""
        if not self.player: 
            return "break"
            
        if getattr(self, 'in_sync_mode', False):
            d_time = 1.0 if e.delta < 0 else -1.0
            if self.settings.get("inv_scroll_time", False): 
                d_time *= -1
            self.seek_relative(d_time)
            return "break"
            
        if not self.shft_ts: 
            return "break"
            
        direction = 1 if e.delta < 0 else -1
        if self.settings.get("inv_scroll_line", False): 
            direction *= -1
            
        ci = -1
        for i, (t, _) in enumerate(self.shft_ts):
            if self.interpolated_time >= t: 
                ci = i
            else: 
                break
                
        ni = max(0, min(len(self.shft_ts) - 1, ci + direction))
        
        if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped]: 
            self.player.stop()
            self.player.play()
            
        self.player.set_time(int(self.shft_ts[ni][0] * 1000))
        self.last_drawn_curr = -1
        self.update_loop_logic()
        return "break"

    def seek_to_line(self, event, txt_widget, col_type):
        """Forces audio progression pointer to specifically designated line metadata."""
        if not self.player: 
            return
        try:
            line_idx = int(txt_widget.index(f"@{event.x},{event.y}").split('.')[0]) - 1
            if col_type == "SYNC":
                line = txt_widget.get(f"{line_idx+1}.0", f"{line_idx+1}.end")
                m = LRC_REGEX.search(line)
                if m:
                    mn, sc, d = m.groups()
                    t = int(mn)*60 + int(sc) + float(f"0.{d}")
                    if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped]: 
                        self.player.play()
                        self.player.set_pause(1)
                    self.player.set_time(int(t * 1000))
                    self.last_drawn_curr = -1
                    self.update_loop_logic()
                self.sync_current_line = line_idx
                self.highlight_sync_line()
                return
                
            for t, idx in (self.orig_ts if col_type == "ORIGINAL" else self.shft_ts):
                if idx == line_idx:
                    if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped]: 
                        self.player.play()
                        self.player.set_pause(1)
                    self.player.set_time(int(t * 1000))
                    self.last_drawn_curr = -1
                    self.update_loop_logic()
                    break
        except Exception: 
            pass

    def copy_txt(self, p, w, pf):
        if p:
            self.root.clipboard_clear()
            self.root.clipboard_append(os.path.splitext(os.path.basename(p))[0])
            original_text = w.cget("text")
            w.config(text=f"{pf}COPIED!", fg="#42f542")
            self.root.after(800, lambda: w.config(text=original_text, fg=get_colors(self.settings["theme"])[1]))

    def copy_dir(self, p, w, pf):
        if p:
            self.root.clipboard_clear()
            self.root.clipboard_append(os.path.dirname(p))
            original_text = w.cget("text")
            w.config(text=f"{pf}COPIED!", fg="#42f542")
            self.root.after(800, lambda: w.config(text=original_text, fg=get_colors(self.settings["theme"])[1]))

    def copy_timer(self):
        if self.player:
            m, s = divmod(self.interpolated_time, 60)
            text_stamp = f"[{int(m):02d}:{int(s):02d}.{int(round((self.interpolated_time % 1) * 100)):02d}]"
            self.root.clipboard_clear()
            self.root.clipboard_append(text_stamp)
            self.timer_msg.config(text=text_stamp)
            self.root.after(2000, lambda: self.timer_msg.config(text=""))

    def seek_relative(self, seconds):
        if not self.player or self.duration <= 0: 
            return
        if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped]:
            self.player.play()
            self.player.set_pause(1)
            self.player.set_time(0)
            self.interpolated_time = 0.0
            self.last_os_time = time.time()
            
        current = self.interpolated_time
        new_time = max(0, min(self.duration, current + seconds))
        self.player.set_time(int(new_time * 1000))
        self.last_drawn_curr = -1
        self.update_loop_logic()

    def on_seek(self, event):
        """Allows visual scrubbing along the progress canvas."""
        if not self.player or self.duration <= 0: 
            return
        self.is_seeking = True
        w = self.seek_canvas.winfo_width()
        if w <= 0: 
            return
            
        x_val = max(0, min(event.x, w))
        self.interpolated_time = (x_val / w) * self.duration
        self._draw_seek(self.interpolated_time)
        self.time_label.config(text=f"{self._fmt(self.interpolated_time)} / {self._fmt(self.duration)}")
        
        curr = self.interpolated_time
        self.handle_highs(self.left_col, self.orig_ts, curr, self.auto_scroll_orig, "last_act_orig", False, {})
        self.handle_highs(self.right_col, self.shft_ts, curr, self.auto_scroll_shft, "last_act_shft", False, self.local_offsets)
        
        if getattr(self, 'in_sync_mode', False): 
            self.draw_sync_gutter()

    def on_seek_release(self, event=None):
        """Confirms timeline skip operation on release of visual element."""
        if self.player and self.duration > 0: 
            if self.player.get_state() in [vlc.State.Stopped, vlc.State.Ended]:
                self.player.play()
                self.player.set_pause(1)
            self.player.set_time(int(self.interpolated_time * 1000))
            self.is_seeking = False
            self.last_vlc_time = self.player.get_time() / 1000.0
            self.last_os_time = time.time()

    def toggle_playback(self):
        if not self.player: 
            return
        if self.player.get_state() == vlc.State.Ended:
            self.player.stop()
            self.player.set_media(self.instance.media_new(self.audio_path))
            self.player.audio_set_volume(self.settings.get("volume", 75))
            self.player.play()
            self.interpolated_time = 0.0
            self.last_drawn_curr = -1
            self.last_os_time = time.time()
        elif self.player.is_playing():
            self.player.set_pause(1)
        else:
            self.player.set_pause(0)
            self.last_os_time = time.time()
        self.update_loop_logic()

    def toggle_all_autoscroll(self):
        new_state = not self.auto_scroll_orig.get()
        self.auto_scroll_orig.set(new_state)
        self.auto_scroll_shft.set(new_state)

    def create_shortcut(self):
        if os.name != 'nt': 
            return
        try:
            icon_png = os.path.join(APP_DIR, "ProgramThumbnail.png")
            icon_ico = os.path.join(APP_DIR, "ProgramThumbnail.ico")
            
            if os.path.exists(icon_png) and not os.path.exists(icon_ico):
                try: 
                    img = Image.open(icon_png)
                    img.save(icon_ico, format='ICO', sizes=[(256, 256)])
                except Exception: 
                    pass
                    
            desk = os.path.join(os.environ['USERPROFILE'], 'Desktop')
            vbs_p = os.path.join(desk, "LRC_Editor.vbs")
            
            vbs_content = (
                f'Set ws = CreateObject("WScript.Shell")\n'
                f'Set s = ws.CreateShortcut("{desk}\\LRC Editor.lnk")\n'
                f's.TargetPath = "{sys.executable if getattr(sys, "frozen", False) else "pythonw.exe"}"\n'
                f's.Arguments = "{"" if getattr(sys, "frozen", False) else f"{os.path.abspath(sys.argv[0])}"}"\n'
                f's.WorkingDirectory = "{APP_DIR}"'
            )
            
            if os.path.exists(icon_ico): 
                vbs_content += f'\ns.IconLocation = "{icon_ico}"'
                
            with open(vbs_p, "w") as f:
                f.write(vbs_content + '\ns.Save')
                
            os.system(f'cscript //nologo "{vbs_p}"')
            os.remove(vbs_p)
            messagebox.showinfo("Success", "Shortcut created on Desktop!")
        except Exception as e: 
            messagebox.showerror("Error", str(e))

    def show_first_run(self):
        """Displays initialization configuration window for newly deployed applications."""
        win = tk.Toplevel(self.root)
        win.title("Welcome to LRC Editor")
        win.geometry("500x650")
        win.grab_set()
        center_window(win)
        
        bg_col, fg_col, box_col, track_col = get_colors(self.settings["theme"])
        win.config(bg=bg_col)
        
        try:
            logo_p = os.path.join(APP_DIR, "logo.png")
            if os.path.exists(logo_p):
                img = Image.open(logo_p)
                img.thumbnail((180, 180), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl_img = tk.Label(win, image=photo, bg=bg_col)
                lbl_img.image = photo
                lbl_img.pack(pady=(30, 10))
        except Exception: 
            pass
            
        tk.Label(win, text="Welcome!", font=("Segoe UI", 20, "bold"), bg=bg_col, fg=fg_col).pack()
        tk.Label(win, text="Please choose your preferred theme:", font=("Segoe UI", 11), bg=bg_col, fg=fg_col).pack(pady=10)
        
        tf = tk.Frame(win, bg=bg_col)
        tf.pack(pady=10)
        
        def set_t(t):
            self.apply_theme(t)
            t_bg, t_fg, t_box, t_trk = get_colors(t)
            win.config(bg=t_bg)
            tf.config(bg=t_bg)
            for w in win.winfo_children(): 
                if isinstance(w, tk.Label):
                    w.config(bg=t_bg, fg=t_fg)
                elif isinstance(w, tk.Button) and w.cget("text") not in ["White", "Gray", "OLED", "Start Application"]:
                    w.config(bg=t_box, fg=t_fg, activebackground=t_trk, activeforeground=t_fg)
                    
        tk.Button(tf, text="White", width=12, font="bold", bg="#ffffff", fg="#000000", command=lambda: set_t("White")).pack(side="left", padx=5)
        tk.Button(tf, text="Gray", width=12, font="bold", bg="#1e1e1e", fg="#e0e0e0", command=lambda: set_t("Gray")).pack(side="left", padx=5)
        tk.Button(tf, text="OLED", width=12, font="bold", bg="#000000", fg="#e0e0e0", command=lambda: set_t("OLED")).pack(side="left", padx=5)
        
        tk.Button(win, text="Create Desktop Shortcut", command=self.create_shortcut, bg=box_col, fg=fg_col, font=("Segoe UI", 10, "bold"), activebackground=track_col, activeforeground=fg_col).pack(pady=(30, 10))
        tk.Button(win, text="Start Application", command=win.destroy, bg="#42f542", fg="black", font=("Segoe UI", 12, "bold"), width=20, activebackground="#2ecc2e", activeforeground="black").pack(pady=20)

    def open_files(self):
        """Brings up local OS bridging structures."""
        if "files" in self.open_windows and self.open_windows["files"].winfo_exists(): 
            self.open_windows["files"].lift()
            self.open_windows["files"].focus_set()
            return
            
        win = tk.Toplevel(self.root)
        win.title("File Management")
        win.geometry("500x300")
        center_window(win)
        
        self.open_windows["files"] = win
        self.sub_windows.append(win)
        
        bg_col, fg_col, box_col, track_col = get_colors(self.settings["theme"])
        win.config(bg=bg_col)
        win.bind("<Control-s>", lambda e: win.destroy())
        
        tk.Label(win, text="File Management", font=("Segoe UI", 16, "bold"), bg=bg_col, fg=fg_col).pack(pady=20)
        c = tk.Frame(win, bg=bg_col)
        c.pack(fill="both", expand=True, padx=20, pady=10)
        
        l_f = tk.Frame(c, bg=bg_col)
        l_f.pack(side="left", fill="both", expand=True, padx=10)
        r_f = tk.Frame(c, bg=bg_col)
        r_f.pack(side="left", fill="both", expand=True, padx=10)
        
        tk.Label(l_f, text="AUDIO", font=("Segoe UI", 12, "bold"), bg=bg_col, fg=fg_col).pack(pady=(0,10))
        tk.Label(r_f, text="LRC", font=("Segoe UI", 12, "bold"), bg=bg_col, fg=fg_col).pack(pady=(0,10))
        
        def spawn_btn(parent_frame, text_str, command_func): 
            tk.Button(parent_frame, text=text_str, font=("Segoe UI", 10, "bold"), bg=box_col, fg=fg_col, activebackground=track_col, activeforeground=fg_col, command=lambda: [win.destroy(), command_func()]).pack(fill="x", pady=5)
            
        spawn_btn(l_f, "Open Audio", self.load_audio)
        spawn_btn(l_f, "Save Audio", self.save_audio)
        spawn_btn(l_f, "Save Audio As...", self.save_audio_as)
        
        spawn_btn(r_f, "Open LRC", self.load_lrc_file)
        spawn_btn(r_f, "Import from Audio", self.import_lrc_from_audio)
        spawn_btn(r_f, "Save LRC", self.save_lrc)
        spawn_btn(r_f, "Save LRC As...", self.save_lrc_as)
        
        def force_refresh(b, f, bx, t):
            win.config(bg=b)
            c.config(bg=b)
            l_f.config(bg=b)
            r_f.config(bg=b)
            for parent in [win, c, l_f, r_f]:
                for w in parent.winfo_children():
                    if isinstance(w, tk.Label):
                        w.config(bg=b, fg=f)
                    elif isinstance(w, tk.Button):
                        w.config(bg=bx, fg=f, activebackground=t, activeforeground=f)
                        
        win.custom_refresh = force_refresh

    def set_metadata_edited(self): 
        self.metadata_edited = True
        self.edited_lbl.pack(side="left", padx=10)
        
    def clear_metadata_edited(self): 
        self.metadata_edited = False
        self.edited_lbl.pack_forget()

    def open_metadata(self, e=None):
        """Constructs detailed metadata editor matching specified theme contexts."""
        if not self.audio_path: 
            return messagebox.showinfo("No Audio", "Please open an audio file first to view or edit metadata.")
            
        win = tk.Toplevel(self.root)
        win.title("Audio Metadata")
        center_window(win)
        
        bg_col, fg_col, box_col, track_col = get_colors(self.settings["theme"])
        win.config(bg=bg_col)
        self.sub_windows.append(win)
        
        win.custom_refresh = lambda b, f, bx, t: [
            win.config(bg=b), 
            ttk.Style().configure("TScrollbar", background=bx, troughcolor=b, arrowcolor=f, bordercolor=b)
        ]
        
        top_f = tk.Frame(win, bg=bg_col)
        top_f.pack(fill="x", padx=12, pady=8)
        
        img_f = tk.Frame(top_f, bg=bg_col)
        img_f.pack(side="left", padx=(0, 12))
        
        img_lbl = tk.Label(img_f, text="Click to\nChange Cover", bg=box_col, fg=fg_col, cursor="hand2", font=("Segoe UI", 9), width=15, height=7)
        img_lbl.pack(expand=True, fill="both")
        
        def update_preview(data):
            if data and data != b"DELETE":
                try: 
                    img = Image.open(io.BytesIO(data)).convert("RGBA")
                    max_h = 120
                    orig_w, orig_h = img.size
                    new_w = max(1, int(orig_w * (max_h / orig_h)))
                    try: 
                        img = img.resize((new_w, max_h), Image.Resampling.LANCZOS)
                    except AttributeError: 
                        img = img.resize((new_w, max_h), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    img_lbl.config(image=photo, text="", width=new_w, height=max_h)
                    img_lbl.image = photo
                except Exception: 
                    img_lbl.config(image="", text="Invalid", width=15, height=7)
            else: 
                img_lbl.config(image="", text="No Cover\n(Click)", width=15, height=7)
            
        update_preview(self.pending_cover_data if self.pending_cover_data else self.current_art_data)
        
        def pick_image(event):
            if p := filedialog.askopenfilename(parent=win, filetypes=[("Images", "*.jpg *.jpeg *.png")]):
                try: 
                    with open(p, "rb") as file:
                        d = file.read()
                    self.pending_cover_data = d
                    update_preview(d)
                    self.set_metadata_edited()
                except Exception: 
                    pass
                    
        img_lbl.bind("<Button-1>", pick_image)
        tk.Button(top_f, text="X", font=("Segoe UI", 10, "bold"), bg="#ff4444", fg="white", bd=0, width=3, command=lambda: [setattr(self, 'pending_cover_data', b"DELETE"), update_preview(b"DELETE"), self.set_metadata_edited()]).pack(side="left", anchor="n", pady=2)

        meta = {k: "" for k in META_ORDER}
        try:
            f = File(self.audio_path)
            if self.audio_path.lower().endswith('.mp3'):
                tags = ID3(self.audio_path)
                m = {
                    "TIT2": "Title", "TPE1": "Artist", "TPE2": "Album Artist", "TALB": "Album", 
                    "TYER": "Year", "TDRC": "Year", "TRCK": "Track", "TPOS": "Disc", "TCON": "Genre", 
                    "TBPM": "BPM", "TKEY": "Key", "TOPE": "Original Artist", "TPE4": "Remixed by", 
                    "TCOM": "Composer", "TPE3": "Conductor", "TIT1": "Grouping", "TIT3": "Subtitle", 
                    "TSRC": "ISRC", "TPUB": "Publisher", "TCOP": "Copyright"
                }
                for k, v in tags.items():
                    if k in m: 
                        meta[m[k]] = str(v.text[0]) if hasattr(v, 'text') and v.text else str(v)
                    elif k.startswith("COMM"): 
                        meta["Comment"] = str(v.text[0]) if hasattr(v, 'text') and v.text else str(v)
                    elif k.startswith("TXXX") and getattr(v, 'desc', '') == 'URL': 
                        meta["URL"] = str(v.text[0]) if hasattr(v, 'text') and v.text else str(v)
            else:
                for k, v in (f.tags.items() if f.tags else []):
                    kl, val = k.lower(), str(v[0]) if isinstance(v, list) else str(v)
                    if kl == 'albumartist': kl = 'album artist'
                    if kl == 'tracknumber': kl = 'track'
                    if kl == 'discnumber': kl = 'disc'
                    for om in META_ORDER:
                        if kl == om.lower(): 
                            meta[om] = val
                            break
                    if kl == "date": 
                        meta["Year"] = val
        except Exception: 
            pass
            
        for k in meta:
            if k in self.pending_metadata: 
                meta[k] = self.pending_metadata[k]

        def validate_numeric(text_string): 
            return True if text_string == "" else bool(re.match(r'^[0-9/\-]*$', text_string))
        vcmd = (win.register(validate_numeric), '%P')

        scroll_f = tk.Frame(win, bg=bg_col)
        scroll_f.pack(fill="both", expand=True, padx=8, pady=4)
        
        canvas = tk.Canvas(scroll_f, bg=bg_col, highlightthickness=0)
        sb = ttk.Scrollbar(scroll_f, orient="vertical", command=canvas.yview)
        cont = tk.Frame(canvas, bg=bg_col)
        
        cw_id = canvas.create_window((0, 0), window=cont, anchor="nw")
        
        def on_cont_config(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(cw_id, width=cont.winfo_reqwidth())
            canvas.config(width=cont.winfo_reqwidth(), height=min(600, cont.winfo_reqheight()))
            win.geometry("")
            
        cont.bind("<Configure>", on_cont_config)
        
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        
        def smooth_wheel_scroll(e): 
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
            
        win.bind("<MouseWheel>", smooth_wheel_scroll)
        canvas.bind("<MouseWheel>", smooth_wheel_scroll)

        col1 = tk.Frame(cont, bg=bg_col)
        col1.pack(side="left", fill="both", expand=True, padx=3)
        
        col2 = tk.Frame(cont, bg=bg_col)
        col2.pack(side="left", fill="both", expand=True, padx=3)
        
        def adjust_entry_width(e, ent):
            l = len(ent.get())
            if l > ent.cget("width"):
                ent.config(width=l)
                win.geometry("")

        def make_field(parent, tag):
            r = tk.Frame(parent, bg=bg_col)
            r.pack(fill="x", pady=2)
            tk.Label(r, text=tag+":", font=("Segoe UI", 8, "bold"), width=12, anchor="e", bg=bg_col, fg=self.settings["active_bg"]).pack(side="left", padx=3)
            
            if tag in ["Track", "Disc"]:
                p = (meta[tag] + "/").split("/")[:2]
                e1 = tk.Entry(r, font=("Segoe UI", 9), bg=box_col, fg=fg_col, insertbackground=fg_col, width=5, justify="center", validate='key', validatecommand=vcmd)
                e1.pack(side="left")
                tk.Label(r, text="/", font=("Segoe UI", 9, "bold"), bg=bg_col, fg=fg_col).pack(side="left", padx=1)
                
                e2 = tk.Entry(r, font=("Segoe UI", 9), bg=box_col, fg=fg_col, insertbackground=fg_col, width=5, justify="center", validate='key', validatecommand=vcmd)
                e2.pack(side="left")
                
                e1.insert(0, p[0])
                e2.insert(0, p[1])
                
                def save_split(e=None):
                    v1, v2 = e1.get().strip(), e2.get().strip()
                    val = f"{v1}/{v2}" if v2 else v1
                    self.pending_metadata[tag] = val
                    self.set_metadata_edited()
                    
                e1.bind("<KeyRelease>", save_split)
                e2.bind("<KeyRelease>", save_split)
            else:
                en = tk.Entry(r, font=("Segoe UI", 9), bg=box_col, fg=fg_col, insertbackground=fg_col, validate='key', validatecommand=vcmd if tag in ["Year", "BPM"] else None)
                en.pack(side="left", fill="x", expand=True)
                en.insert(0, meta[tag])
                en.bind("<KeyRelease>", lambda e, n=tag, ent=en: [self.pending_metadata.update({n: ent.get()}), self.set_metadata_edited(), adjust_entry_width(e, ent)])
                
                if tag == "Genre":
                    def ac(e):
                        if e.keysym in ["BackSpace", "Delete", "Return", "Up", "Down"]: 
                            return
                        typed = en.get()
                        for g in GENRES:
                            if g.lower().startswith(typed.lower()):
                                en.delete(0, tk.END)
                                en.insert(0, g)
                                en.select_range(len(typed), tk.END)
                                en.icursor(len(typed))
                                break
                    en.bind("<KeyRelease>", lambda e: [ac(e), self.pending_metadata.update({"Genre": en.get()}), self.set_metadata_edited()])
                    en.bind("<Return>", lambda e: [self.pending_metadata.update({"Genre": en.get()}), self.set_metadata_edited()])

        main_tags = [t for t in META_ORDER if t in self.settings["meta_main"]]
        extra_tags = [t for t in META_ORDER if t not in self.settings["meta_main"]]
        
        tf = tk.Frame(col1, bg=bg_col)
        tf.pack(pady=3, fill="x")
        tk.Label(tf, text="Main Tags", font=("Segoe UI", 9, "bold", "underline"), bg=bg_col, fg=fg_col).pack(side="left")
        
        self.extra_frame = tk.Frame(col2, bg=bg_col)
        
        def toggle_ex():
            if self.extra_frame.winfo_viewable(): 
                self.extra_frame.pack_forget()
                ex_btn.config(text="+")
            else: 
                self.extra_frame.pack(fill="both", expand=True)
                ex_btn.config(text="-")
            win.update_idletasks()
            win.geometry("")
            
        ex_btn = tk.Button(tf, text="+", font=("Segoe UI", 8, "bold"), bg=box_col, fg=fg_col, command=toggle_ex, width=2)
        ex_btn.pack(side="right", padx=6)
        
        for t in main_tags: 
            make_field(col1, t)
            
        tk.Label(self.extra_frame, text="Extra Tags", font=("Segoe UI", 9, "bold", "underline"), bg=bg_col, fg=fg_col).pack(pady=3)
        for t in extra_tags: 
            make_field(self.extra_frame, t)
        
        btn_f = tk.Frame(win, bg=bg_col)
        btn_f.pack(fill="x", padx=12, pady=8)
        
        tk.Button(btn_f, text="Undo All Changes", font=("Segoe UI", 9, "bold"), bg="#ffaa00", fg="black", bd=0, command=lambda: [self.pending_metadata.clear(), setattr(self, 'pending_cover_data', None), self.clear_metadata_edited(), win.destroy(), self.open_metadata()]).pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(btn_f, text="Close", font=("Segoe UI", 9, "bold"), bg=box_col, fg=fg_col, bd=0, command=win.destroy).pack(side="right", expand=True, fill="x", padx=2)
        
        win.update_idletasks()
        win.geometry("")

    def open_appearance(self):
        """Constructs appearance customization dialog with preview functionality."""
        if "appearance" in self.open_windows and self.open_windows["appearance"].winfo_exists(): 
            self.open_windows["appearance"].lift()
            self.open_windows["appearance"].focus_set()
            return
            
        win = tk.Toplevel(self.root)
        win.title("Appearance")
        win.geometry("550x850")
        center_window(win)
        
        win.custom_tag = "appearance_win"
        self.open_windows["appearance"] = win
        self.sub_windows.append(win)
        
        bg_col, fg_col, box_col, track_col = get_colors(self.settings["theme"])
        win.config(bg=bg_col)
        entries = {}
        
        def safe_refresh():
            c_bg, c_fg, c_box, c_track = get_colors(self.settings["theme"])
            win.config(bg=c_bg)
            tf.config(bg=c_bg)
            adj_f.config(bg=c_bg)
            slider_adj_f.config(bg=c_bg)
            slider_pickers_f.config(bg=c_bg)
            
            for parent_frame in [win, adj_f, slider_adj_f, slider_pickers_f]:
                for c in parent_frame.winfo_children():
                    if getattr(c, "custom_tag", "") == "ignore_theme": 
                        continue
                    if isinstance(c, tk.Label): 
                        c.config(bg=c_bg, fg=c_fg)
                    elif isinstance(c, tk.Scale): 
                        c.config(bg=c_bg, fg=c_fg, troughcolor=c_track)
                    elif isinstance(c, tk.Checkbutton): 
                        c.config(bg=c_bg, fg=c_fg, selectcolor=c_box, activebackground=c_bg, activeforeground=c_fg)
                    elif isinstance(c, tk.Frame):
                        c.config(bg=c_bg)
                        for s in c.winfo_children():
                            if getattr(s, "custom_tag", "") == "ignore_theme": 
                                continue
                            if isinstance(s, tk.Label): 
                                s.config(bg=c_bg, fg=c_fg)
                            elif isinstance(s, tk.Checkbutton): 
                                s.config(bg=c_bg, fg=c_fg, selectcolor=c_box, activebackground=c_bg, activeforeground=c_fg)
                            elif isinstance(s, tk.Button): 
                                s.config(bg=c_box, fg=c_fg, activebackground=c_track, activeforeground=c_fg)
                            
            prev_f.config(bg=c_box)
            p_gut.config(bg=c_bg)
            p_txt.config(bg=c_box)
            p_slider.config(bg=c_box)
            
            t_lbl.config(bg=self.settings["count_bg"], fg=self.settings["count_fg"], font=("Consolas", 8, "bold" if self.settings.get("count_bold", True) else "normal"))
            pl_lbl.config(bg=self.settings["played_bg"], fg=self.settings["played_fg"], font=("Consolas", 11, "bold" if self.settings.get("played_bold", False) else "normal"))
            ac_lbl.config(bg=self.settings["active_bg"], fg=self.settings["active_fg"], font=("Consolas", 11, "bold" if self.settings.get("active_bold", True) else "normal"))
            
            s_f = ("Consolas", 11, "bold" if self.settings.get("sync_bold", True) else "normal")
            sync_lbl.config(bg=self.settings.get("sync_bg", "#ffaa00"), fg=self.settings.get("sync_fg", "#000000"), font=s_f)
            
            self.apply_theme(self.settings["theme"])
            
            for k, ent in entries.items():
                if ent.winfo_exists():
                    try: 
                        ent.config(bg=self.settings[k], fg=get_contrast(self.settings[k]))
                        ent.delete(0, tk.END)
                        ent.insert(0, self.settings[k])
                    except Exception: 
                        pass
                    
            btn_w.config(bg="#ffffff", fg="#000000", activebackground="#cccccc", activeforeground="#000000")
            btn_g.config(bg="#1e1e1e", fg="#e0e0e0", activebackground="#2a2a2a", activeforeground="#ffffff")
            btn_o.config(bg="#000000", fg="#e0e0e0", activebackground="#111111", activeforeground="#ffffff")
            
            p_slider.update()
            pw_w = p_slider.winfo_width()
            if pw_w < 10: 
                pw_w = 400
            ph = 20
            p_slider.delete("all")
            
            if self.settings.get("slider_sync", True):
                u_c = c_box
                p_c = self.settings["played_bg"]
                t_c = self.settings["active_bg"]
                t_b = get_contrast(t_c)
            else:
                u_c = self.settings.get("slider_bg", "#1a1a1a")
                p_c = self.settings.get("slider_played", "#42f542")
                t_c = self.settings.get("slider_thumb", "#00ffc3")
                t_b = self.settings.get("slider_thumb_border", "#000000")
                
            p_slider.create_rectangle(0, ph//2 - 4, pw_w, ph//2 + 4, fill=u_c, outline=c_track, width=1)
            pw_fill = int(pw_w * 0.5)
            p_slider.create_rectangle(0, ph//2 - 4, pw_fill, ph//2 + 4, fill=p_c, outline=c_track, width=1)
            p_slider.create_rectangle(pw_fill - 6, 2, pw_fill + 6, ph - 2, fill=t_c, outline=t_b, width=2)
            
            if hasattr(self, 'seek_canvas'): 
                self._draw_seek(self.interpolated_time)
        
        tk.Label(win, text="THEME", font=("Segoe UI", 12, "bold"), bg=bg_col, fg=fg_col).pack(pady=(15, 5))
        tf = tk.Frame(win, bg=bg_col)
        tf.pack(pady=5)
        
        btn_w = tk.Button(tf, text="White", width=10, bg="#ffffff", fg="#000000", command=lambda: [self.settings.update({"theme": "White"}), self.save_settings(), safe_refresh()])
        btn_w.custom_tag = "ignore_theme"
        
        btn_g = tk.Button(tf, text="Gray", width=10, bg="#1e1e1e", fg="#e0e0e0", command=lambda: [self.settings.update({"theme": "Gray"}), self.save_settings(), safe_refresh()])
        btn_g.custom_tag = "ignore_theme"
        
        btn_o = tk.Button(tf, text="OLED", width=10, bg="#000000", fg="#e0e0e0", command=lambda: [self.settings.update({"theme": "OLED"}), self.save_settings(), safe_refresh()])
        btn_o.custom_tag = "ignore_theme"
        
        btn_w.pack(side="left", padx=5)
        btn_g.pack(side="left", padx=5)
        btn_o.pack(side="left", padx=5)
            
        tk.Frame(win, height=1, bg="gray").pack(fill="x", pady=10, padx=30)
        tk.Label(win, text="COLOR ADJUSTMENT", font=("Segoe UI", 12, "bold"), bg=bg_col, fg=fg_col).pack(pady=(0, 5))
        adj_f = tk.Frame(win, bg=bg_col)
        adj_f.pack(fill="x", padx=20)
        
        def make_row(parent, label, bg_k, fg_k, bold_k=None):
            row = tk.Frame(parent, bg=bg_col)
            row.pack(fill="x", pady=5)
            tk.Label(row, text=label, width=12, anchor="e", font=("Segoe UI", 10, "bold"), bg=bg_col, fg=fg_col).pack(side="left", padx=(0, 10))
            tk.Button(row, text="BG" if fg_k else "COLOR", width=5 if fg_k else 6, bg=box_col, fg=fg_col, activebackground=track_col, activeforeground=fg_col, command=lambda: [self.settings.update({bg_k: colorchooser.askcolor(initialcolor=self.settings.get(bg_k, "#ffffff"), parent=win)[1] or self.settings.get(bg_k, "#ffffff")}), self.save_settings(), safe_refresh()]).pack(side="left")
            
            ebg = tk.Entry(row, width=8, bg=self.settings.get(bg_k, "#ffffff"), fg=get_contrast(self.settings.get(bg_k, "#ffffff")), bd=0, highlightthickness=1)
            ebg.pack(side="left", padx=5)
            entries[bg_k] = ebg
            
            if fg_k:
                tk.Button(row, text="FG", width=4, bg=box_col, fg=fg_col, activebackground=track_col, activeforeground=fg_col, command=lambda: [self.settings.update({fg_k: colorchooser.askcolor(initialcolor=self.settings.get(fg_k, "#ffffff"), parent=win)[1] or self.settings.get(fg_k, "#ffffff")}), self.save_settings(), safe_refresh()]).pack(side="left", padx=(10, 0))
                efg = tk.Entry(row, width=8, bg=self.settings.get(fg_k, "#ffffff"), fg=get_contrast(self.settings.get(fg_k, "#ffffff")), bd=0, highlightthickness=1)
                efg.pack(side="left", padx=5)
                entries[fg_k] = efg
                efg.bind("<KeyRelease>", lambda e: [self.settings.update({fg_k: efg.get()}), self.save_settings(), safe_refresh()] if len(efg.get())==7 else None)
                
            ebg.bind("<KeyRelease>", lambda e: [self.settings.update({bg_k: ebg.get()}), self.save_settings(), safe_refresh()] if len(ebg.get())==7 else None)
            
            if bold_k:
                bv = tk.BooleanVar(value=self.settings.get(bold_k, False))
                tk.Checkbutton(row, text="Bold", variable=bv, bg=bg_col, fg=fg_col, selectcolor=box_col, activebackground=bg_col, activeforeground=fg_col, command=lambda: [self.settings.update({bold_k: bv.get()}), self.save_settings(), safe_refresh()]).pack(side="left", padx=10)
            
        make_row(adj_f, "Active Line:", "active_bg", "active_fg", "active_bold")
        make_row(adj_f, "Played Line:", "played_bg", "played_fg", "played_bold")
        make_row(adj_f, "Sync Line:", "sync_bg", "sync_fg", "sync_bold")
        make_row(adj_f, "Timer:", "count_bg", "count_fg", "count_bold")
        
        tk.Frame(win, height=1, bg="gray").pack(fill="x", pady=10, padx=30)
        tk.Label(win, text="SLIDER ADJUSTMENT", font=("Segoe UI", 12, "bold"), bg=bg_col, fg=fg_col).pack(pady=(0, 5))
        slider_adj_f = tk.Frame(win, bg=bg_col)
        slider_adj_f.pack(fill="x", padx=20)
        sync_var = tk.BooleanVar(value=self.settings.get("slider_sync", True))
        slider_pickers_f = tk.Frame(slider_adj_f, bg=bg_col)
        
        def toggle_sync():
            self.settings["slider_sync"] = sync_var.get()
            self.save_settings()
            if sync_var.get():
                slider_pickers_f.pack_forget()
            else:
                slider_pickers_f.pack(fill="x")
            safe_refresh()
            
        tk.Checkbutton(slider_adj_f, text="Sync Slider with Line Colors", variable=sync_var, bg=bg_col, fg=fg_col, selectcolor=box_col, activebackground=bg_col, activeforeground=fg_col, command=toggle_sync).pack(pady=2)
        make_row(slider_pickers_f, "Unplayed BG:", "slider_bg", None)
        make_row(slider_pickers_f, "Played BG:", "slider_played", None)
        make_row(slider_pickers_f, "Thumb Color:", "slider_thumb", None)
        make_row(slider_pickers_f, "Thumb Border:", "slider_thumb_border", None)
        
        if not sync_var.get(): 
            slider_pickers_f.pack(fill="x")

        tk.Frame(win, height=1, bg="gray").pack(fill="x", pady=10, padx=30)
        tk.Label(win, text="PREVIEW", font=("Segoe UI", 10, "bold"), bg=bg_col, fg=fg_col).pack(pady=(0, 5))
        prev_f = tk.Frame(win, bd=1, relief="sunken")
        prev_f.pack(fill="x", padx=40, pady=5)
        p_gut = tk.Frame(prev_f, width=50)
        p_gut.pack(side="left", fill="y")
        p_gut.pack_propagate(False)
        t_lbl = tk.Label(p_gut, text="1.5s")
        t_lbl.place(relx=0.5, rely=0.5, anchor="center")
        p_txt = tk.Frame(prev_f)
        p_txt.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        pl_lbl = tk.Label(p_txt, text="[00:10.00] This line was played", anchor="w")
        pl_lbl.pack(fill="x")
        ac_lbl = tk.Label(p_txt, text="[00:13.50] This is the active line", anchor="w")
        ac_lbl.pack(fill="x")
        sync_lbl = tk.Label(p_txt, text="[00:15.00] This is the sync line", anchor="w")
        sync_lbl.pack(fill="x")
        p_slider = tk.Canvas(p_txt, height=20, bg=box_col, highlightthickness=0)
        p_slider.pack(side="bottom", fill="x", pady=(10, 5))
        
        tk.Frame(win, height=1, bg="gray").pack(fill="x", pady=10, padx=30)
        tk.Label(win, text="THUMBNAIL MAX HEIGHT", font=("Segoe UI", 10, "bold"), bg=bg_col, fg=fg_col).pack(pady=(0, 5))
        thumb_scale = tk.Scale(win, from_=200, to=400, orient="horizontal", highlightthickness=0, bd=0, bg=bg_col, fg=fg_col, troughcolor=track_col, activebackground=bg_col, command=self.update_thumb_size)
        thumb_scale.set(self.settings.get("thumb_size", 200))
        thumb_scale.pack(fill="x", padx=50)
        safe_refresh()

    def open_settings(self):
        if "settings" in self.open_windows and self.open_windows["settings"].winfo_exists(): 
            self.open_windows["settings"].lift()
            self.open_windows["settings"].focus_set()
            return
            
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.geometry("500x650")
        center_window(win)
        
        self.open_windows["settings"] = win
        bg_col, fg_col, box_col, track_col = get_colors(self.settings["theme"])
        win.config(bg=bg_col)
        self.sub_windows.append(win)
        win.custom_refresh = lambda b, f, bx, t: win.config(bg=b)
        
        tk.Label(win, text="DEFAULT MUSIC FOLDER", font=("Segoe UI", 12, "bold"), bg=bg_col, fg=fg_col).pack(pady=(15, 5))
        dir_f = tk.Frame(win, bg=bg_col)
        dir_f.pack(fill="x", padx=20)
        dir_var = tk.StringVar(value=self.settings.get("default_music_dir", ""))
        tk.Entry(dir_f, textvariable=dir_var, bg=box_col, fg=fg_col, width=40).pack(side="left", padx=5)
        
        def browse_dir():
            if d := filedialog.askdirectory(parent=win): 
                dir_var.set(d)
                self.settings["default_music_dir"] = d
                self.save_settings()
                
        tk.Button(dir_f, text="Browse", bg=box_col, fg=fg_col, command=browse_dir).pack(side="left")
        dir_var.trace("w", lambda *a: self.settings.update({"default_music_dir": dir_var.get()}) or self.save_settings())
        
        tk.Label(win, text="SCROLL OPTIONS", font=("Segoe UI", 12, "bold"), bg=bg_col, fg=fg_col).pack(pady=(15, 5))
        for k, txt in [("inv_scroll_time", "Invert Global Scroll (Seek +/- 1s)"), ("inv_scroll_line", "Invert Shift+Scroll (Prev/Next Line)")]:
            v = tk.BooleanVar(value=self.settings[k])
            tk.Checkbutton(win, text=txt, variable=v, bg=bg_col, fg=fg_col, selectcolor=box_col, activebackground=bg_col, activeforeground=fg_col, command=lambda key=k, var=v: [self.settings.update({key: var.get()}), self.save_settings()]).pack(pady=2)

        tk.Label(win, text="FILE IO OPTIONS", font=("Segoe UI", 12, "bold"), bg=bg_col, fg=fg_col).pack(pady=(15, 5))
        auto_v = tk.BooleanVar(value=self.settings.get("auto_open_saved", True))
        tk.Checkbutton(win, text="Auto-load file after saving", variable=auto_v, bg=bg_col, fg=fg_col, selectcolor=box_col, activebackground=bg_col, activeforeground=fg_col, command=lambda: [self.settings.update({"auto_open_saved": auto_v.get()}), self.save_settings()]).pack(pady=2)
        
        tk.Label(win, text="MAIN METADATA TAGS", font=("Segoe UI", 12, "bold"), bg=bg_col, fg=fg_col).pack(pady=(15, 5))
        tk.Label(win, text="Checked tags appear in the main metadata window.\nUnchecked move to 'Show More'.", font=("Segoe UI", 9, "italic"), bg=bg_col, fg=self.settings["active_bg"]).pack()
        tags_f = tk.Frame(win, bg=bg_col)
        tags_f.pack(fill="both", expand=True, padx=20, pady=10)
        
        def toggle_main_tag(tag, state):
            if state and tag not in self.settings["meta_main"]: 
                self.settings["meta_main"].append(tag)
            elif not state and tag in self.settings["meta_main"]: 
                self.settings["meta_main"].remove(tag)
            self.settings["meta_main"].sort(key=lambda x: META_ORDER.index(x) if x in META_ORDER else 99)
            self.save_settings()
            
        for i, t in enumerate(META_ORDER):
            v = tk.BooleanVar(value=t in self.settings["meta_main"])
            cb = tk.Checkbutton(tags_f, text=t, variable=v, bg=bg_col, fg=fg_col, selectcolor=box_col, activebackground=bg_col, activeforeground=fg_col)
            cb.grid(row=i//3, column=i%3, sticky="w", padx=10, pady=2)
            cb.config(command=lambda tag=t, var=v: toggle_main_tag(tag, var.get()))
            
        tk.Button(win, text="Create Desktop Shortcut", command=self.create_shortcut, bg=box_col, fg=fg_col, activebackground=track_col, activeforeground=fg_col, font=("Segoe UI", 9, "bold")).pack(pady=20)

    def open_hotkeys(self):
        """Displays formatted and categorized hotkey assignments."""
        if "hotkeys" in self.open_windows and self.open_windows["hotkeys"].winfo_exists(): 
            self.open_windows["hotkeys"].lift()
            self.open_windows["hotkeys"].focus_set()
            return
            
        win = tk.Toplevel(self.root)
        win.title("Hotkeys Configuration")
        win.geometry("650x750")
        center_window(win)
        
        self.open_windows["hotkeys"] = win
        bg_col, fg_col, box_col, track_col = get_colors(self.settings["theme"])
        win.config(bg=bg_col)
        self.sub_windows.append(win)
        win.custom_refresh = lambda b, f, bx, t: win.config(bg=b)
        
        win.bind("<Control-h>", lambda e: win.destroy())
        win.bind("<Alt-h>", lambda e: win.destroy())
        
        wrapper = tk.Frame(win, bg=bg_col)
        wrapper.pack(fill="both", expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(wrapper, bg=bg_col, highlightthickness=0)
        scrollbar = tk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        container = tk.Frame(canvas, bg=bg_col)
        container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas.create_window((0, 0), window=container, anchor="nw", width=610)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        def smooth_wheel(e): 
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
            
        win.bind("<MouseWheel>", smooth_wheel)
        canvas.bind("<MouseWheel>", smooth_wheel)

        row_idx = 0
        for group_name, keys in HOTKEY_GROUPS.items():
            tk.Label(
                container, 
                text=group_name, 
                font=("Segoe UI", 12, "bold", "underline"), 
                bg=bg_col, 
                fg=self.settings["active_bg"]
            ).grid(row=row_idx, column=0, columnspan=3, pady=(15, 5), sticky="w")
            row_idx += 1
            
            for key in keys:
                if key not in self.settings["hotkeys"]: 
                    continue
                conf = self.settings["hotkeys"][key]
                r_bg = box_col if row_idx % 2 == 0 else bg_col
                
                f = tk.Frame(container, bg=r_bg)
                f.grid(row=row_idx, column=0, columnspan=3, sticky="ew", pady=1)
                
                desc_ent = tk.Entry(f, font=("Segoe UI", 10), bg=r_bg, fg=fg_col, width=30, bd=0, highlightthickness=1)
                desc_ent.insert(0, conf["desc"])
                desc_ent.pack(side="left", padx=10, pady=6)
                
                bind_ent = tk.Entry(f, font=("Consolas", 10, "bold"), bg=r_bg, fg=self.settings["active_bg"], width=18, bd=0, highlightthickness=1, justify="center")
                bind_ent.insert(0, conf["bind"])
                bind_ent.pack(side="left", padx=10, pady=6)
                
                en_var = tk.BooleanVar(value=conf["enabled"])
                cb_btn = tk.Button(f, font=("Consolas", 10, "bold"), width=6, bd=0)
                cb_btn.pack(side="left", padx=15, pady=6)
                
                def update_hk_visuals(e_var, d_ent, b_ent, btn, c_box, c_trk):
                    if e_var.get():
                        d_ent.config(fg=get_colors(self.settings["theme"])[1])
                        b_ent.config(fg=self.settings["active_bg"])
                        btn.config(text="[ ON ]", fg="#42f542", bg=c_box, activebackground=c_trk, activeforeground="#42f542")
                    else:
                        d_ent.config(fg="#666666")
                        b_ent.config(fg="#666666")
                        btn.config(text="[OFF]", fg="#ff4444", bg=c_box, activebackground=c_trk, activeforeground="#ff4444")

                def save_hk(e=None, k=key, d=desc_ent, b=bind_ent, ev=en_var, btn=cb_btn):
                    if e is None: 
                        ev.set(not ev.get()) 
                    self.settings["hotkeys"][k] = {"bind": b.get().strip(), "desc": d.get().strip(), "enabled": ev.get()}
                    self.save_settings()
                    self.bind_all_hotkeys()
                    self.setup_menu()
                    update_hk_visuals(ev, d, b, btn, get_colors(self.settings["theme"])[2], get_colors(self.settings["theme"])[3])
                    
                desc_ent.bind("<KeyRelease>", save_hk)
                bind_ent.bind("<KeyRelease>", save_hk)
                cb_btn.config(command=save_hk)
                update_hk_visuals(en_var, desc_ent, bind_ent, cb_btn, box_col, track_col)
                row_idx += 1

    def open_hidden_gimmicks(self):
        """Hidden fun document logic."""
        if "gimmicks" in self.open_windows and self.open_windows["gimmicks"].winfo_exists(): 
            self.open_windows["gimmicks"].lift()
            self.open_windows["gimmicks"].focus_set()
            return
            
        win = tk.Toplevel(self.root)
        win.title("Hidden Gimmicks")
        win.geometry("620x520")
        center_window(win)
        
        self.open_windows["gimmicks"] = win
        bg_col, fg_col, box_col, track_col = get_colors(self.settings["theme"])
        win.config(bg=bg_col)
        
        txt = tk.Text(win, bg=bg_col, fg=fg_col, font=("Segoe UI", 10), wrap="word", bd=0, padx=15, pady=15)
        txt.pack(fill="both", expand=True)
        
        try:
            with open(HIDDEN_GIMMICKS_FILE, "r", encoding="utf-8") as f: 
                content = f.read()
        except Exception: 
            if os.path.exists(HIDDEN_GIMMICKS_FILE):
                content = "Could not load HiddenGimmicks.txt"
            else:
                content = "HiddenGimmicks.txt not found in program directory."
                
        txt.insert("1.0", content)
        txt.config(state="disabled")

    def open_about(self):
        """Displays About information and handles link generation."""
        if "about" in self.open_windows and self.open_windows["about"].winfo_exists(): 
            self.open_windows["about"].lift()
            self.open_windows["about"].focus_set()
            return
            
        win = tk.Toplevel(self.root)
        win.title("About")
        win.geometry("450x350")
        center_window(win)
        
        bg_col, fg_col, box_col, track_col = get_colors(self.settings["theme"])
        win.config(bg=bg_col)
        self.open_windows["about"] = win
        self.sub_windows.append(win)
        win.custom_refresh = lambda b, f, bx, t: win.config(bg=b)
        
        try:
            logo_p = os.path.join(APP_DIR, "logo.png")
            if os.path.exists(logo_p):
                img = Image.open(logo_p)
                img.thumbnail((150, 150), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                lbl_img = tk.Label(win, image=photo, bg=bg_col)
                lbl_img.image = photo
                lbl_img.pack(pady=(20, 10))
                
            about_p = os.path.join(APP_DIR, "about.txt")
            if os.path.exists(about_p):
                with open(about_p, "r", encoding="utf-8") as f: 
                    content = f.read().strip()
                txt = tk.Text(win, bg=bg_col, fg=fg_col, font=("Segoe UI", 10), wrap="word", bd=0, highlightthickness=0, height=8)
                txt.pack(padx=20, pady=10, fill="both", expand=True)
                txt.insert("1.0", content)
                txt.tag_config("link", foreground="#00ffc3", underline=True)
                txt.tag_bind("link", "<Enter>", lambda e: txt.config(cursor="hand2"))
                txt.tag_bind("link", "<Leave>", lambda e: txt.config(cursor=""))
                txt.tag_bind("link", "<Button-1>", lambda e: webbrowser.open(txt.get(tk.SEL_FIRST, tk.SEL_LAST) if txt.tag_ranges(tk.SEL) else URL_REGEX.search(txt.get("1.0", tk.END)).group(1)))
                
                for match in URL_REGEX.finditer(content): 
                    txt.tag_add("link", f"1.0 + {match.start()} chars", f"1.0 + {match.end()} chars")
                txt.config(state="disabled")
        except Exception: 
            pass

    def load_lrc_file(self, e=None):
        if path := filedialog.askopenfilename(initialdir=self._get_init_dir(), filetypes=[("LRC Files", "*.lrc")]): 
            self._reload_lrc(path)
            
    def _reload_lrc(self, path):
        if getattr(self, 'in_sync_mode', False): 
            self.exit_sync_mode(save=False)
            
        self.lrc_path = path
        self.lrc_name_lab.config(text=f"LRC File: {os.path.basename(path)}")
        self.lrc_path_lab.config(text=f"Path: {os.path.dirname(path)}")
        
        try: 
            with open(path, "r", encoding="utf-8", errors="replace") as file:
                self.lrc_from_file = file.read().replace("\r\n", "\n").replace("\r", "\n")
        except Exception: 
            pass
            
        self.src_var.set("file")
        self.refresh_views()

    def load_audio(self, e=None):
        if path := filedialog.askopenfilename(initialdir=self._get_init_dir(), filetypes=[("Audio", "*.mp3 *.flac *.wav *.m4a")]): 
            self._reload_audio(path)
            
    def _reload_audio(self, path):
        if getattr(self, 'in_sync_mode', False): 
            self.exit_sync_mode(save=False)
            
        self.audio_path = path
        self.audio_name_lab.config(text=f"File Name: {os.path.basename(path)}")
        self.audio_path_lab.config(text=f"Path: {os.path.dirname(path)}")
        self.pending_metadata.clear()
        self.pending_cover_data = None
        self.clear_metadata_edited()
        
        try:
            af = File(path)
            size = os.path.getsize(path)/(1024*1024)
            if hasattr(af, 'info') and hasattr(af.info, 'bitrate'):
                br = f"{int(af.info.bitrate/1000)} kbps"
            else:
                br = "VBR"
            self.tech_info_lab.config(text=f"Size: {size:.1f} MB | Bitrate: {br}")
        except Exception: 
            pass
        
        if self.player: 
            self.player.stop()
            
        self.player = self.instance.media_player_new()
        self.player.set_media(self.instance.media_new(path))
        self.player.audio_set_volume(self.settings.get("volume", 75))
        
        self.lrc_from_meta = self._get_meta_lyrics(path)
        
        lrc_p = os.path.splitext(path)[0] + ".lrc"
        if os.path.exists(lrc_p):
            self.lrc_path = lrc_p
            self.lrc_name_lab.config(text=f"LRC File: {os.path.basename(lrc_p)}")
            self.lrc_path_lab.config(text=f"Path: {os.path.dirname(lrc_p)}")
            try: 
                with open(lrc_p, "r", encoding="utf-8", errors="replace") as file:
                    self.lrc_from_file = file.read().replace("\r\n", "\n").replace("\r", "\n")
            except Exception: 
                pass
            self.src_var.set("file")
        elif self.lrc_from_meta: 
            self.src_var.set("meta")
        
        self.refresh_views()
        self.refresh_thumbnail()
        
        self.is_loading = True
        self.player.play()
        self._poll_len_and_pause()

    def _poll_len_and_pause(self, tries=0):
        """Asynchronously waits for VLC to load media into buffer."""
        if not self.player: 
            return
            
        length = self.player.get_length()
        if length > 0:
            self.duration = length / 1000.0
            self.player.set_pause(1)
            self.player.set_time(0)
            self.last_vlc_time = 0.0
            self.interpolated_time = 0.0
            self.last_drawn_curr = -1
            self.root.after(150, lambda: setattr(self, 'is_loading', False))
        elif tries < 50:
            self.root.after(100, lambda: self._poll_len_and_pause(tries+1))

    def _get_meta_lyrics(self, path):
        """Extracts native lyrics strictly directly from files."""
        try:
            audio_file = File(path)
            if path.lower().endswith('.mp3'):
                tags = ID3(path)
                for key in tags.keys():
                    if key.startswith('USLT'): 
                        return str(tags[key].text).replace("\r\n", "\n").replace("\r", "\n")
            if audio_file.tags:
                for target_key in ['LYRICS', 'lyrics', 'UNSYNCEDLYRICS']:
                    if target_key in audio_file.tags: 
                        return str(audio_file.tags[target_key][0]).replace("\r\n", "\n").replace("\r", "\n")
        except Exception: 
            pass
        return ""

    def save_lrc(self, e=None):
        if not self.lrc_path: 
            return self.save_lrc_as()
        try:
            with open(self.lrc_path, "w", encoding="utf-8") as file:
                file.write(self.right_col["txt"].get("1.0", "end-1c"))
            messagebox.showinfo("Saved", f"LRC Saved to:\n{self.lrc_path}")
            if self.settings.get("auto_open_saved", True): 
                self._reload_lrc(self.lrc_path)
        except Exception as e: 
            messagebox.showerror("Error", str(e))

    def save_lrc_as(self, e=None):
        if path := filedialog.asksaveasfilename(defaultextension=".lrc", filetypes=[("LRC", "*.lrc")]): 
            self.lrc_path = path
            self.save_lrc()

    def save_audio(self, e=None):
        if not self.audio_path: 
            return
        self._apply_audio_metadata(self.audio_path)
        self.clear_metadata_edited()
        messagebox.showinfo("Saved", "Audio metadata and lyrics updated successfully.")
        if self.settings.get("auto_open_saved", True): 
            self._reload_audio(self.audio_path)

    def save_audio_as(self, e=None):
        if not self.audio_path: 
            return
        ext = os.path.splitext(self.audio_path)[1]
        if new_path := filedialog.asksaveasfilename(defaultextension=ext, filetypes=[("Audio", f"*{ext}")]):
            try:
                shutil.copy2(self.audio_path, new_path)
                self._apply_audio_metadata(new_path)
                messagebox.showinfo("Saved", f"Audio Saved to:\n{new_path}")
                if self.settings.get("auto_open_saved", True): 
                    self._reload_audio(new_path)
            except Exception as e: 
                messagebox.showerror("Error", str(e))

    def _apply_audio_metadata(self, target_path):
        """Bakes pending attributes directly into physical media item natively."""
        try:
            audio_file = File(target_path)
            if audio_file is None: 
                return
                
            lyrics_text = self.right_col["txt"].get("1.0", "end-1c")
            
            if target_path.lower().endswith('.mp3'):
                try: 
                    tags = ID3(target_path)
                except Exception: 
                    tags = ID3()
                    
                mapping = {
                    "Title": TIT2, "Artist": TPE1, "Album Artist": TPE2, "Album": TALB, 
                    "Year": TDRC, "Track": TRCK, "Disc": TPOS, "Genre": TCON, "BPM": TBPM, 
                    "Key": TKEY, "Original Artist": TOPE, "Remixed by": TPE4, "Composer": TCOM, 
                    "Conductor": TPE3, "Grouping": TIT1, "Subtitle": TIT3, "ISRC": TSRC, 
                    "Publisher": TPUB, "Copyright": TCOP, "Encoded by": TENC
                }
                
                for k, v in self.pending_metadata.items():
                    if k == "Comment" and v.strip(): 
                        tags.add(COMM(encoding=3, lang='eng', desc='', text=[v]))
                    elif k == "URL" and v.strip(): 
                        tags.add(TXXX(encoding=3, desc='URL', text=[v]))
                    elif k in mapping and v.strip(): 
                        tags.add(mapping[k](encoding=3, text=[v]))
                    elif k not in mapping and v.strip(): 
                        tags.add(TXXX(encoding=3, desc=k, text=[v]))
                        
                if lyrics_text.strip(): 
                    tags.delall('USLT')
                    tags.add(USLT(encoding=3, lang='eng', desc='', text=lyrics_text))
                else: 
                    tags.delall('USLT')
                
                if self.pending_cover_data == b"DELETE": 
                    tags.delall('APIC')
                elif self.pending_cover_data: 
                    tags.delall('APIC')
                    tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=self.pending_cover_data))
                    
                tags.save(target_path)
            else:
                if not hasattr(audio_file, 'tags') or audio_file.tags is None: 
                    audio_file.add_tags()
                    
                for k, v in self.pending_metadata.items():
                    if v.strip():
                        tag_name = k.upper().replace(" ", "")
                        if tag_name == "YEAR": 
                            tag_name = "DATE"
                        elif tag_name == "TRACK": 
                            tag_name = "TRACKNUMBER"
                        elif tag_name == "DISC": 
                            tag_name = "DISCNUMBER"
                        audio_file.tags[tag_name] = [v]
                        
                if lyrics_text.strip(): 
                    audio_file.tags['LYRICS'] = [lyrics_text]
                elif 'LYRICS' in audio_file.tags: 
                    del audio_file.tags['LYRICS']
                
                if self.pending_cover_data == b"DELETE": 
                    audio_file.clear_pictures()
                elif self.pending_cover_data and target_path.lower().endswith('.flac'):
                    pic = Picture()
                    pic.type, pic.mime, pic.desc, pic.data = 3, "image/jpeg", "Cover", self.pending_cover_data
                    audio_file.clear_pictures()
                    audio_file.add_picture(pic)
                    
                audio_file.save()
        except Exception as e: 
            messagebox.showerror("Error saving metadata", str(e))

    def refresh_views(self):
        """Re-draws all graphical UI lists with active offset states."""
        self.left_col["txt"].config(state="normal")
        self.left_col["txt"].delete("1.0", tk.END)
        src = self.src_var.get()
        
        if src == "file" and self.lrc_from_file: 
            self.left_col["txt"].insert("1.0", self.lrc_from_file)
        elif src == "meta" and self.lrc_from_meta: 
            self.left_col["txt"].insert("1.0", self.lrc_from_meta)
            
        # VERY IMPORTANT: This is the ONLY place where true_original_text is set from a file load.
        self.true_original_text = self.left_col["txt"].get("1.0", "end-1c")
        
        lines_count = int(self.left_col["txt"].index("end-1c").split('.')[0])
        self.line_tracker = list(range(1, lines_count + 1))
        self.local_offsets.clear()
        self.apply_offset()

    def refresh_thumbnail(self):
        """Scans current track memory for potential album cover objects."""
        if not self.audio_path: 
            return
        self.current_art_data = None
        try:
            audio_file = File(self.audio_path)
            data = None
            if hasattr(audio_file, 'pictures') and audio_file.pictures: 
                data = audio_file.pictures[0].data
            elif hasattr(audio_file, 'tags') and audio_file.tags:
                if 'APIC:' in audio_file.tags: 
                    data = audio_file.tags['APIC:'].data
                else:
                    for k, v in audio_file.tags.items():
                        if k.startswith('APIC') or k == 'COVR':
                            data = v.data if hasattr(v, 'data') else v[0]
                            break
            if data:
                self.current_art_data = data
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                size = self.settings.get("thumb_size", 200)
                
                orig_w, orig_h = img.size
                new_h = size
                new_w = max(1, int(orig_w * (size / orig_h)))
                
                try: 
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                except AttributeError: 
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                
                self.cover_img = ImageTk.PhotoImage(img)
                self.art_label.config(image=self.cover_img, text="", width=new_w, height=new_h)
            else: 
                self.art_label.config(image='', text="No Cover", width=0, height=0)
        except Exception: 
            self.art_label.config(image='', text="Error Cover", width=0, height=0)

    def apply_offset(self, preview_local=None):
        """The heart of the application: shifting timings based on global + local modifications."""
        pos = self.right_col["txt"].yview()
        raw = self.left_col["txt"].get("1.0", "end-1c")
        
        if hasattr(self, 'true_original_text'):
            # Show RESTORE button if currently active left text is different from what was initially loaded
            if raw.strip() != self.true_original_text.strip():
                if not self.btn_restore_orig.winfo_ismapped(): 
                    self.btn_restore_orig.pack(side="right", padx=5)
            else:
                if self.btn_restore_orig.winfo_ismapped(): 
                    self.btn_restore_orig.pack_forget()
            
        try:
            off = int(self.off_m_var.get() or 0)*60 + int(self.off_s_var.get() or 0) + int(self.off_ms_var.get() or 0)/10.0
            if self.settings["offset_sign"] == "-": 
                off = -off
        except Exception: 
            off = 0.0
            
        new_lines, self.orig_ts, self.shft_ts, self.has_time_errors = [], [], [], False
        lo_dict = preview_local
        
        if lo_dict is None:
            if self.ctx_menu and self.ctx_menu.winfo_exists(): 
                lo_dict = self.temp_local_offsets
            else: 
                lo_dict = self.local_offsets
            
        for i, line in enumerate(raw.split("\n")):
            m = LRC_REGEX.search(line)
            if m:
                mn, sc, d = m.groups()
                t_o = int(mn)*60 + int(sc) + float(f"0.{d}")
                self.orig_ts.append((t_o, i))
                t_n = max(0, t_o + off + lo_dict.get(i, 0.0))
                self.shft_ts.append((t_n, i))
                nm, ns = divmod(int(t_n), 60)
                new_lines.append(LRC_REGEX.sub(f"[{nm:02d}:{ns:02d}.{int((t_n*10)%10)}]", line))
            else: 
                new_lines.append(line)
            
        self.right_col["txt"].config(state="normal")
        self.right_col["txt"].delete("1.0", tk.END)
        self.right_col["txt"].insert("1.0", "\n".join(new_lines))
        self.right_col["txt"].config(state="disabled")
        self.right_col["txt"].yview_moveto(pos[0])
        self.left_col["char_lbl"].config(text=f"Characters: {len(raw)}")
        self.right_col["char_lbl"].config(text=f"Characters: {len(self.right_col['txt'].get('1.0', tk.END).strip())}")
        
        self.orig_time_errors = self._get_time_errors_lis(self.orig_ts)
        self.shft_time_errors = self._get_time_errors_lis(self.shft_ts)
        self.has_time_errors = len(self.shft_time_errors) > 0

        for c_txt, errs in [(self.left_col["txt"], self.orig_time_errors), (self.right_col["txt"], self.shft_time_errors)]:
            c_txt.tag_remove("time_err", "1.0", tk.END)
            for idx in errs:
                start = f"{idx+1}.0"
                pos = c_txt.search(r"\[\d{2}:\d{2}\.\d+\]", start, stopindex=f"{idx+1}.end", regexp=True)
                if pos:
                    m_txt = c_txt.get(pos, f"{idx+1}.end")
                    m = LRC_REGEX.search(m_txt)
                    if m:
                        match_len = len(m.group(0))
                        c_txt.tag_add("time_err", pos, f"{pos}+{match_len}c")
        
        if self.has_time_errors:
            self.btn_sort.pack(side="left", padx=10)
        else:
            self.btn_sort.pack_forget()
            
        self.handle_highs(self.right_col, self.shft_ts, self.interpolated_time, self.auto_scroll_shft, "last_act_shft", True, lo_dict)

    def update_loop(self):
        """Asynchronous system loop forcing consistent timeline logic checking."""
        self.update_loop_logic()
        self.root.after(10, self.update_loop)

    def update_loop_logic(self):
        """Interacts seamlessly matching player hardware state against visual representations."""
        if self.player and not getattr(self, 'is_loading', False) and not getattr(self, 'is_seeking', False):
            p_state = self.player.get_state()
            vt = max(0, self.player.get_time() / 1000.0)
            now = time.time()
            
            if p_state == vlc.State.Ended or (self.duration > 0 and vt > 0 and vt >= self.duration - 0.05):
                self.player.stop()
                self.player.set_media(self.instance.media_new(self.audio_path))
                self.player.audio_set_volume(self.settings.get("volume", 75))
                self.player.play()
                if not getattr(self, 'loop_track', False):
                    self.player.set_pause(1)
                vt = 0.0
                self.last_vlc_time = 0.0
                self.interpolated_time = 0.0
                self.last_os_time = time.time()
                self.last_drawn_curr = -1
            else:
                if vt != self.last_vlc_time: 
                    self.last_vlc_time, self.last_os_time, self.interpolated_time = vt, now, vt
                elif self.player.is_playing(): 
                    self.interpolated_time = min(self.duration, vt + (now - self.last_os_time))
                    
            curr = self.interpolated_time
            self.btn_play.config(text="PAUSE" if self.player.is_playing() else "PLAY")
            self.time_label.config(text=f"{self._fmt(curr)} / {self._fmt(self.duration)}")
            
            if abs(curr - self.last_drawn_curr) > 0.05: 
                self._draw_seek(curr)
                self.last_drawn_curr = curr
                
            self.handle_highs(self.left_col, self.orig_ts, curr, self.auto_scroll_orig, "last_act_orig", False, {})
            self.handle_highs(self.right_col, self.shft_ts, curr, self.auto_scroll_shft, "last_act_shft", False, self.local_offsets)
            
            if getattr(self, 'in_sync_mode', False): 
                self.draw_sync_gutter()

    def _draw_seek(self, curr):
        """Constructs progress slider dynamics strictly bound by appearance inputs."""
        if not hasattr(self, 'seek_canvas') or self.duration <= 0: 
            return
        w = self.seek_canvas.winfo_width()
        if w <= 10:
            return
            
        h = self.seek_canvas.winfo_height()
        theme_colors = get_colors(self.settings["theme"])
        
        if self.settings.get("slider_sync", True):
            unplayed_color = theme_colors[2]
            played_color = self.settings["played_bg"]
            thumb_color = self.settings["active_bg"]
            thumb_border = get_contrast(thumb_color)
        else:
            unplayed_color = self.settings.get("slider_bg", "#1a1a1a")
            played_color = self.settings.get("slider_played", "#42f542")
            thumb_color = self.settings.get("slider_thumb", "#00ffc3")
            thumb_border = self.settings.get("slider_thumb_border", "#000000")
            
        border_color = theme_colors[3]
        pw = int(w * min(1.0, max(0.0, curr / self.duration)))
        
        self.seek_canvas.delete("all")
        self.seek_canvas.create_rectangle(0, h//2 - 4, w, h//2 + 4, fill=unplayed_color, outline=border_color, width=1)
        if pw > 0: 
            self.seek_canvas.create_rectangle(0, h//2 - 4, pw, h//2 + 4, fill=played_color, outline=border_color, width=1)
        if pw > 0:
            thumb_w = 6
            self.seek_canvas.create_rectangle(pw - thumb_w, 2, pw + thumb_w, h - 2, fill=thumb_color, outline=thumb_border, width=2)

    def handle_highs(self, col, ts_data, curr, scroll_v, last_attr, force, lo_dict):
        """Triggers tag adjustments to ensure visual lines strictly adhere to chronological playback."""
        if getattr(self, 'in_sync_mode', False) and col == self.right_col: 
            return
            
        txt = col["txt"]
        gut = col["gut"]
        active = -1
        n_idx = -1
        n_t = 0
        
        for t, idx in ts_data:
            if curr >= t - 0.02: 
                active = idx
            else: 
                n_idx = idx
                n_t = t - curr
                break
                
        last_act = getattr(self, last_attr)
        if active != last_act or force:
            txt.tag_remove("active", "1.0", tk.END)
            txt.tag_remove("played", "1.0", tk.END)
            if active != -1:
                txt.tag_add("played", "1.0", f"{active+1}.0")
                txt.tag_add("active", f"{active+1}.0", f"{active+1}.end")
                if scroll_v.get() and active != last_act: 
                    txt.yview_moveto(max(0, (active - 8) / max(1, int(txt.index("end-1c").split(".")[0]))))
            setattr(self, last_attr, active)
            
        gut.delete("all")
        try:
            is_orig = (col == self.left_col)
            for ln in range(int(txt.index("@0,0").split(".")[0]), int(txt.index(f"@0,{txt.winfo_height()}").split(".")[0]) + 2):
                bbox = txt.bbox(f"{ln}.0")
                if bbox:
                    y = bbox[1]
                    if hasattr(self, 'line_tracker') and (ln-1) < len(self.line_tracker):
                        orig_ln = self.line_tracker[ln-1]
                    else:
                        orig_ln = ln
                        
                    is_err_order = (orig_ln != ln)
                    
                    gut.create_text(15, y+10, text=str(ln), fill="gray", font="Consolas 8")
                    gut.create_text(35, y+10, text=str(orig_ln), fill="#ff4444" if is_err_order else "gray", font="Consolas 8")
                    
                    if not is_orig:
                        if (ln-1) in lo_dict and lo_dict[ln-1] != 0:
                            lo = lo_dict[ln-1]
                            gut.create_text(65, y+10, text=f"{'+' if lo > 0 else ''}{lo:.1f}s", fill="#42f542" if lo > 0 else "#ff4444", font=("Consolas", 7, "bold"))
                            
                        if ln == n_idx + 1 and n_t > 0.05:
                            gut.create_rectangle(80, y+2, 115, y+18, fill=self.settings["count_bg"], outline="")
                            gut.create_text(97, y+10, text=f"{n_t:.1f}s", fill=self.settings["count_fg"], font=("Consolas", 8, "bold" if self.settings.get("count_bold", True) else "normal"))
        except Exception: 
            pass

    def _fmt(self, t): 
        m, s = divmod(int(max(0, t)), 60)
        return f"{m:02d}:{s:02d}.{int((t%1)*100):02d}"

if __name__ == "__main__":
    root = tk.Tk()
    app = LRCTimeShifter(root)
    root.mainloop()