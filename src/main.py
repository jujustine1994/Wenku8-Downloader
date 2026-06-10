import ctypes
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from src.config import OUTPUT_DIR, RETRY_COUNT, RETRY_DELAY
from src.scraper import parse_aid_from_url, fetch_catalog, parse_book_title, parse_volumes
from src.downloader import run_download_all

# 高 DPI 感知（4K/2K 螢幕不模糊，需在 Tk() 前呼叫）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SCRIPT_DIR, ".tool_config.json")


def resolve_output_dir(config: dict, project_root: str) -> str:
    raw = config.get("output_dir", "").strip()
    if raw:
        return raw
    return os.path.join(project_root, OUTPUT_DIR)

F  = ("Microsoft JhengHei", 12)
FS = ("Microsoft JhengHei", 11)
FB = ("Microsoft JhengHei", 12, "bold")
FM = ("Consolas", 12)
FH = ("Microsoft JhengHei", 10)

URL_PLACEHOLDER = "https://www.wenku8.net/modules/article/reader.php?aid=XXXX"

THEMES = {
    "light": {
        "name": "清爽白",
        "sv": "light",
        "log_bg": "#F4F4F4", "log_fg": "#333333",
        "frame_title": "#1A6BAF", "label_fg": "",
        "btn_bg": "#0078D4", "btn_fg": "#FFFFFF",
        "win_bg": "#F3F3F3", "card_bg": "#FFFFFF",
        "border": "#D0D0D0", "pbar": "#0078D4",
    },
    "dark": {
        "name": "深色模式",
        "sv": "dark",
        "log_bg": "#1A1A1A", "log_fg": "#C8C8C8",
        "frame_title": "#60AAFF", "label_fg": "",
        "btn_bg": "#3A7BD5", "btn_fg": "#FFFFFF",
        "win_bg": "#202020", "card_bg": "#2A2A2A",
        "border": "#444444", "pbar": "#4A90E2",
    },
    "financial": {
        "name": "金融藍",
        "sv": "light",
        "log_bg": "#F0F5FF", "log_fg": "#1B2B45",
        "frame_title": "#1B3A6B", "label_fg": "#1B3A6B",
        "btn_bg": "#1B3A6B", "btn_fg": "#F5C518",
        "win_bg": "#EEF2F8", "card_bg": "#FFFFFF",
        "border": "#BDD0EA", "pbar": "#1B3A6B",
    },
}


def show_cth_banner():
    b = "\033[90m"
    c = "\033[96m"
    y = "\033[93m"
    r = "\033[0m"
    print(f"{b}/*  ================================  *\\{r}")
    print(f"{b} *                                    *{r}")
    print(f"{b} *    {c}██████╗████████╗██╗  ██╗{b}        *{r}")
    print(f"{b} *   {c}██╔════╝   ██║   ██║  ██║{b}        *{r}")
    print(f"{b} *   {c}██║        ██║   ███████║{b}        *{r}")
    print(f"{b} *   {c}██║        ██║   ██╔══██║{b}        *{r}")
    print(f"{b} *   {c}╚██████╗   ██║   ██║  ██║{b}        *{r}")
    print(f"{b} *    {c}╚═════╝   ╚═╝   ╚═╝  ╚═╝{b}        *{r}")
    print(f"{b} *                                    *{r}")
    print(f"{b} *          {y}created by CTH{b}            *{r}")
    print(f"{b}\\*  ================================  */{r}")
    print()


def _conv_worker(
    files: list[str], output_mode: str, msg_queue: queue.Queue
) -> None:
    from src.converter import run_convert_all
    run_convert_all(files, output_mode, msg_queue)


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Wenku8 Downloader")
        self.root.resizable(True, True)
        self.root.minsize(800, 640)

        self.msg_queue: queue.Queue = queue.Queue()
        self._volumes = []
        self._fail_volumes: list = []
        self._conv_files: list[str] = []
        self._aid = None
        self._book_name = None
        _cfg = self._load_config()
        self._current_theme = _cfg.get("theme", "light")
        self._path_var = tk.StringVar()
        self._retry_count = int(_cfg.get("retry_count", RETRY_COUNT))
        self._retry_delay = int(_cfg.get("retry_delay", RETRY_DELAY))
        self._browsing = False

        self._build_ui()
        self._path_var.set(resolve_output_dir(_cfg, PROJECT_ROOT))
        self._apply_theme(self._current_theme)
        self._poll_queue()

    def _build_ui(self):
        pad = {"padx": 14, "pady": 6}
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self._notebook = ttk.Notebook(self.root)
        self._notebook.grid(row=0, column=0, sticky="nsew")

        tab_download = ttk.Frame(self._notebook)
        self._notebook.add(tab_download, text="  下載  ")
        tab_download.columnconfigure(0, weight=1)
        tab_download.rowconfigure(1, weight=1)
        tab_download.rowconfigure(3, weight=1)

        # === URL 輸入區 ===
        frame_url = ttk.LabelFrame(tab_download, text=" 書籍目錄網址 ", padding=8)
        frame_url.grid(row=0, column=0, sticky="ew", **pad)
        frame_url.columnconfigure(0, weight=1)

        url_row = ttk.Frame(frame_url)
        url_row.pack(fill="x")
        url_row.columnconfigure(0, weight=1)

        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var, font=FS)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.btn_load = ttk.Button(url_row, text="載入", command=self._on_load, width=8)
        self.btn_load.grid(row=0, column=1)
        ttk.Button(url_row, text="⚙", command=self._open_settings, width=4).grid(
            row=0, column=2, padx=(4, 0)
        )

        folder_row = ttk.Frame(frame_url)
        folder_row.pack(fill="x", pady=(6, 0))
        folder_row.columnconfigure(1, weight=1)

        ttk.Label(folder_row, text="下載至：", font=FS).grid(row=0, column=0, sticky="w")
        path_entry = ttk.Entry(folder_row, textvariable=self._path_var, font=FS)
        path_entry.grid(row=0, column=1, sticky="ew", padx=(4, 8))
        path_entry.bind("<Return>", self._on_path_confirm)
        path_entry.bind("<FocusOut>", self._on_path_confirm)
        ttk.Button(
            folder_row, text="瀏覽", command=self._on_browse_folder, width=6
        ).grid(row=0, column=2)

        # === 卷列表（勾選清單）===
        frame_volumes = ttk.LabelFrame(tab_download, text=" 卷列表 ", padding=8)
        frame_volumes.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 6))
        frame_volumes.columnconfigure(0, weight=1)
        frame_volumes.rowconfigure(1, weight=1)

        self.title_label = ttk.Label(
            frame_volumes, text="（輸入網址後點「載入」）", font=FS
        )
        self.title_label.grid(row=0, column=0, sticky="w", pady=(0, 4))

        # Canvas + scrollbar for checkbox list
        list_outer = ttk.Frame(frame_volumes)
        list_outer.grid(row=1, column=0, sticky="nsew")
        list_outer.columnconfigure(0, weight=1)
        list_outer.rowconfigure(0, weight=1)

        self._check_canvas = tk.Canvas(list_outer, highlightthickness=0, height=180)
        cb_sb = ttk.Scrollbar(list_outer, orient="vertical", command=self._check_canvas.yview)
        self._check_canvas.configure(yscrollcommand=cb_sb.set)
        self._check_canvas.grid(row=0, column=0, sticky="nsew")
        cb_sb.grid(row=0, column=1, sticky="ns")

        self._cb_frame = ttk.Frame(self._check_canvas)
        self._cb_window = self._check_canvas.create_window(
            (0, 0), window=self._cb_frame, anchor="nw"
        )
        self._cb_frame.bind(
            "<Configure>",
            lambda e: self._check_canvas.configure(
                scrollregion=self._check_canvas.bbox("all")
            ),
        )
        self._check_canvas.bind(
            "<Configure>",
            lambda e: self._check_canvas.itemconfig(self._cb_window, width=e.width),
        )
        self._check_canvas.bind("<MouseWheel>", self._on_canvas_scroll)

        self._check_vars: list[tk.BooleanVar] = []

        # Button row: 全選 | 全不選 | (spacer) | 下載選取
        btn_row = ttk.Frame(frame_volumes)
        btn_row.grid(row=2, column=0, sticky="ew", pady=(6, 0))

        self.btn_select_all = ttk.Button(
            btn_row, text="全選", width=6, state="disabled",
            command=lambda: self._select_all(True),
        )
        self.btn_select_all.pack(side="left", ipady=4, padx=(0, 4))
        self.btn_deselect_all = ttk.Button(
            btn_row, text="全不選", width=6, state="disabled",
            command=lambda: self._select_all(False),
        )
        self.btn_deselect_all.pack(side="left", ipady=4)
        self.btn_download = ttk.Button(
            btn_row, text="下載選取", command=self._on_download, width=10, state="disabled"
        )
        self.btn_download.pack(side="right", ipady=4)
        self.btn_retry = ttk.Button(
            btn_row, text="重試失敗", command=self._on_retry, width=10, state="disabled"
        )
        self.btn_retry.pack(side="right", ipady=4, padx=(0, 6))

        # === 進度 ===
        frame_progress = ttk.LabelFrame(tab_download, text=" 進度 ", padding=8)
        frame_progress.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))
        frame_progress.columnconfigure(0, weight=1)

        self.progress_label = ttk.Label(frame_progress, text="等待中...", font=FS)
        self.progress_label.pack(anchor="w")
        self.progress_bar = ttk.Progressbar(frame_progress, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(4, 0))

        # === 記錄 ===
        frame_log = ttk.LabelFrame(tab_download, text=" 記錄 ", padding=8)
        frame_log.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 6))
        frame_log.columnconfigure(0, weight=1)
        frame_log.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            frame_log, width=60, height=8, state="disabled", font=FM
        )
        self.log_text.pack(fill="both", expand=True)

        tab_convert = ttk.Frame(self._notebook)
        self._notebook.add(tab_convert, text="  轉換  ")
        self._build_convert_tab(tab_convert)

        # === Status Bar ===
        sep = ttk.Separator(self.root, orient="horizontal")
        sep.grid(row=98, column=0, sticky="ew")
        self._status_bar = tk.Label(
            self.root, text="就緒", anchor="w", padx=10, pady=4,
            font=FS, foreground="gray"
        )
        self._status_bar.grid(row=99, column=0, sticky="ew")
        # 防止長錯誤訊息撐寬視窗：讓 label 跟著視窗寬度折行而非撐大視窗
        def _on_root_resize(e):
            if e.widget is not self.root:
                return
            w = self.root.winfo_width()
            self._status_bar.config(wraplength=w - 20)
            self.title_label.config(wraplength=w - 40)
        self.root.bind("<Configure>", _on_root_resize)

    def _build_convert_tab(self, tab: ttk.Frame):
        pad = {"padx": 14, "pady": 6}
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        tab.rowconfigure(3, weight=1)

        # Header：計數 + 選擇檔案按鈕
        frame_header = ttk.Frame(tab)
        frame_header.grid(row=0, column=0, sticky="ew", **pad)
        frame_header.columnconfigure(0, weight=1)

        self._conv_count_label = ttk.Label(
            frame_header, text="未選擇任何檔案", font=FS
        )
        self._conv_count_label.grid(row=0, column=0, sticky="w")
        ttk.Button(
            frame_header, text="選擇檔案", command=self._on_conv_select, width=10
        ).grid(row=0, column=1)

        # 檔案列表（可捲動）
        frame_files = ttk.LabelFrame(tab, text=" 檔案列表 ", padding=8)
        frame_files.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 6))
        frame_files.columnconfigure(0, weight=1)
        frame_files.rowconfigure(0, weight=1)

        self._conv_canvas = tk.Canvas(frame_files, highlightthickness=0, height=120)
        conv_sb = ttk.Scrollbar(
            frame_files, orient="vertical", command=self._conv_canvas.yview
        )
        self._conv_canvas.configure(yscrollcommand=conv_sb.set)
        self._conv_canvas.grid(row=0, column=0, sticky="nsew")
        conv_sb.grid(row=0, column=1, sticky="ns")

        self._conv_file_frame = ttk.Frame(self._conv_canvas)
        self._conv_file_window = self._conv_canvas.create_window(
            (0, 0), window=self._conv_file_frame, anchor="nw"
        )
        self._conv_file_frame.bind(
            "<Configure>",
            lambda e: self._conv_canvas.configure(
                scrollregion=self._conv_canvas.bbox("all")
            ),
        )
        self._conv_canvas.bind(
            "<Configure>",
            lambda e: self._conv_canvas.itemconfig(
                self._conv_file_window, width=e.width
            ),
        )
        self._conv_canvas.bind("<MouseWheel>", self._on_canvas_scroll)

        # 輸出模式 + 開始按鈕
        frame_output = ttk.Frame(tab)
        frame_output.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))

        ttk.Label(frame_output, text="輸出：", font=FS).pack(side="left")
        self._conv_output_var = tk.StringVar(value="overwrite")
        ttk.Radiobutton(
            frame_output, text="覆蓋原檔",
            variable=self._conv_output_var, value="overwrite"
        ).pack(side="left", padx=(0, 16))
        ttk.Radiobutton(
            frame_output, text="另存新檔（加 _TC 後綴）",
            variable=self._conv_output_var, value="new_file"
        ).pack(side="left")

        self._conv_btn = ttk.Button(
            frame_output, text="開始轉換",
            command=self._on_conv_start, width=10, state="disabled"
        )
        self._conv_btn.pack(side="right")

        # 記錄區
        frame_conv_log = ttk.LabelFrame(tab, text=" 記錄 ", padding=8)
        frame_conv_log.grid(row=3, column=0, sticky="nsew", padx=14, pady=(0, 6))
        frame_conv_log.columnconfigure(0, weight=1)
        frame_conv_log.rowconfigure(0, weight=1)

        self._conv_log = scrolledtext.ScrolledText(
            frame_conv_log, width=60, height=6,
            state="disabled", font=FM
        )
        self._conv_log.pack(fill="both", expand=True)

    def _on_conv_select(self):
        from tkinter import filedialog
        chosen = filedialog.askopenfilenames(
            title="選擇 TXT 檔案",
            filetypes=[("文字檔案", "*.txt"), ("所有檔案", "*.*")],
        )
        for path in chosen:
            if path not in self._conv_files:
                self._conv_files.append(path)
        self._refresh_conv_file_list()

    def _conv_remove_file(self, path: str):
        self._conv_files.remove(path)
        self._refresh_conv_file_list()

    def _refresh_conv_file_list(self):
        for w in self._conv_file_frame.winfo_children():
            w.destroy()
        for path in self._conv_files:
            row = ttk.Frame(self._conv_file_frame)
            row.pack(fill="x", padx=4, pady=1)
            row.columnconfigure(0, weight=1)
            ttk.Label(row, text=path, font=FS, anchor="w").grid(
                row=0, column=0, sticky="ew"
            )
            ttk.Button(
                row, text="移除", width=5,
                command=lambda p=path: self._conv_remove_file(p),
            ).grid(row=0, column=1, padx=(4, 0))
        n = len(self._conv_files)
        self._conv_count_label.config(
            text=f"已選 {n} 個檔案" if n > 0 else "未選擇任何檔案"
        )
        self._conv_btn.config(state="normal" if n > 0 else "disabled")
        self._conv_canvas.yview_moveto(0)

    def _on_conv_start(self):
        if not self._conv_files:
            return
        files = list(self._conv_files)
        output_mode = self._conv_output_var.get()
        self._conv_btn.config(state="disabled")
        self._conv_log.config(state="normal")
        self._conv_log.delete("1.0", "end")
        self._conv_log.config(state="disabled")
        self._set_status(f"轉換中... 共 {len(files)} 個檔案", "info")
        threading.Thread(
            target=_conv_worker,
            args=(files, output_mode, self.msg_queue),
            daemon=True,
        ).start()

    def _set_status(self, msg: str, level: str = "info"):
        self.msg_queue.put(("status", (msg, level)))

    def _on_browse_folder(self):
        from tkinter import filedialog
        self._browsing = True
        try:
            current = self._path_var.get()
            initial = current if os.path.isdir(current) else PROJECT_ROOT
            chosen = filedialog.askdirectory(initialdir=initial, title="選擇下載資料夾")
            if chosen:
                self._path_var.set(chosen)
                self._save_config({"output_dir": chosen})
                self._set_status(f"下載位置：{chosen}", "success")
        finally:
            self._browsing = False

    def _on_path_confirm(self, event=None):
        if self._browsing:
            return
        path = self._path_var.get().strip()
        self._path_var.set(path)
        if os.path.isdir(path):
            self._save_config({"output_dir": path})
            self._set_status(f"下載位置：{path}", "info")
        else:
            self._set_status(f"路徑不存在：{path}（下載時會自動建立）", "info")

    # ---- 主題 ----

    def _apply_theme(self, theme_key: str):
        t = THEMES.get(theme_key, THEMES["light"])
        try:
            import sv_ttk
            sv_ttk.set_theme(t["sv"])
        except ImportError:
            pass

        from tkinter import font as tkfont
        for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(fname).configure(family="Microsoft JhengHei", size=12)

        style = ttk.Style()
        style.configure("TButton", font=F)
        style.configure("TEntry", font=F)
        style.configure("TCombobox", font=F)
        style.configure("TLabelframe.Label", font=F, foreground=t["frame_title"])
        label_fg = t["label_fg"]
        for w in ("TLabel", "TCheckbutton", "TRadiobutton"):
            kw = {"font": F}
            if label_fg:
                kw["foreground"] = label_fg
            style.configure(w, **kw)

        self.log_text.config(bg=t["log_bg"], fg=t["log_fg"], insertbackground=t["log_fg"])
        self._conv_log.config(bg=t["log_bg"], fg=t["log_fg"], insertbackground=t["log_fg"])
        self._current_theme = theme_key

    # ---- 設定視窗 ----

    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("設定")
        win.resizable(False, False)
        win.grab_set()

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=16, pady=(12, 0))

        tab_appearance = ttk.Frame(notebook, padding=12)
        notebook.add(tab_appearance, text="  外觀  ")
        left = ttk.Frame(tab_appearance)
        left.pack(side="left", anchor="n", padx=(0, 16))
        right = ttk.Frame(tab_appearance)
        right.pack(side="left", anchor="n")

        ttk.Label(left, text="配色主題").pack(anchor="w", pady=(0, 10))
        theme_var = tk.StringVar(value=self._current_theme)
        for key, info in THEMES.items():
            ttk.Radiobutton(
                left, text=info["name"], variable=theme_var, value=key
            ).pack(anchor="w", pady=4)

        preview = tk.Canvas(right, width=210, height=168, highlightthickness=1,
                            highlightbackground="#CCCCCC")
        preview.pack()
        ttk.Label(right, text="預覽", foreground="gray").pack(pady=(4, 0))

        def draw_preview(key):
            t = THEMES.get(key, THEMES["light"])
            c = preview
            c.delete("all")
            W, H = 210, 168
            c.create_rectangle(0, 0, W, H, fill=t["win_bg"], outline="")
            tbar_bg = t["card_bg"] if t["sv"] == "light" else "#2D2D2D"
            c.create_rectangle(0, 0, W, 22, fill=tbar_bg, outline="")
            c.create_text(10, 11, text="Wenku8 Downloader", anchor="w",
                          fill=t["frame_title"], font=("Microsoft JhengHei", 7, "bold"))
            c.create_rectangle(8, 28, W - 8, 68, fill=t["card_bg"], outline=t["border"])
            c.create_text(16, 33, text=" 書籍目錄網址 ", anchor="w",
                          fill=t["frame_title"], font=("Microsoft JhengHei", 7, "bold"))
            c.create_rectangle(16, 44, W - 16, 58, fill=t["log_bg"], outline=t["border"])
            bx1, bx2 = 65, 145
            c.create_rectangle(bx1, 74, bx2, 88, fill=t["btn_bg"], outline="")
            c.create_text((bx1 + bx2) // 2, 81, text="下載全部",
                          fill=t["btn_fg"], font=("Microsoft JhengHei", 7))
            c.create_rectangle(8, 94, W - 8, H - 6, fill=t["card_bg"], outline=t["border"])
            c.create_text(16, 99, text=" 進度 ", anchor="w",
                          fill=t["frame_title"], font=("Microsoft JhengHei", 7, "bold"))
            bar_bg = "#E5E5E5" if t["sv"] == "light" else "#3A3A3A"
            c.create_rectangle(16, 110, W - 16, 116, fill=bar_bg, outline="")
            c.create_rectangle(16, 110, 70, 116, fill=t["pbar"], outline="")
            c.create_rectangle(16, 122, W - 16, H - 12, fill=t["log_bg"], outline=t["border"])
            c.create_text(20, 128, text="等待中...", anchor="nw", fill=t["log_fg"],
                          font=("Microsoft JhengHei", 7))

        theme_var.trace_add("write", lambda *_: draw_preview(theme_var.get()))
        draw_preview(self._current_theme)

        tab_download = ttk.Frame(notebook, padding=12)
        notebook.add(tab_download, text="  下載  ")

        row1 = ttk.Frame(tab_download)
        row1.pack(fill="x", pady=(0, 12))
        ttk.Label(row1, text="重試次數：", font=F).pack(side="left")
        retry_count_var = tk.IntVar(value=self._retry_count)
        ttk.Spinbox(
            row1, from_=1, to=10, textvariable=retry_count_var,
            width=5, font=F
        ).pack(side="left", padx=(8, 4))
        ttk.Label(row1, text="次", font=F).pack(side="left")

        row2 = ttk.Frame(tab_download)
        row2.pack(fill="x")
        ttk.Label(row2, text="重試間隔：", font=F).pack(side="left")
        retry_delay_var = tk.IntVar(value=self._retry_delay)
        ttk.Spinbox(
            row2, from_=1, to=30, textvariable=retry_delay_var,
            width=5, font=F
        ).pack(side="left", padx=(8, 4))
        ttk.Label(row2, text="秒", font=F).pack(side="left")

        def _apply():
            self._apply_theme(theme_var.get())
            self._retry_count = retry_count_var.get()
            self._retry_delay = retry_delay_var.get()
            self._save_config({
                "theme": theme_var.get(),
                "retry_count": self._retry_count,
                "retry_delay": self._retry_delay,
            })
            win.destroy()

        btn_row = ttk.Frame(win)
        btn_row.pack(pady=(12, 16))
        ttk.Button(btn_row, text="套用", command=_apply, width=10).pack(
            side="left", padx=4, ipady=4
        )
        ttk.Button(btn_row, text="取消", command=win.destroy, width=10).pack(
            side="left", padx=4, ipady=4
        )

    # ---- 設定檔 ----

    def _load_config(self) -> dict:
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_config(self, data: dict):
        try:
            cfg = self._load_config()
            cfg.update(data)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- 勾選清單 ----

    def _build_checkbox_list(self, volumes: list[dict]):
        for w in self._cb_frame.winfo_children():
            w.destroy()
        self._check_vars = []
        pad = max(len(str(len(volumes))), 2)
        for v in volumes:
            var = tk.BooleanVar(value=True)
            self._check_vars.append(var)
            cb = ttk.Checkbutton(
                self._cb_frame,
                text=f"  {str(v['index']).zfill(pad)}  {v['name']}",
                variable=var,
            )
            cb.pack(anchor="w", fill="x", padx=4, pady=1)
            cb.bind("<MouseWheel>", self._on_canvas_scroll)
        self._check_canvas.yview_moveto(0)

    def _select_all(self, state: bool):
        for var in self._check_vars:
            var.set(state)

    def _on_canvas_scroll(self, event):
        self._check_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ---- 載入目錄 ----

    def _on_load(self):
        url = self.url_var.get().strip()
        try:
            aid = parse_aid_from_url(url)
        except ValueError:
            self._set_status("網址格式錯誤，找不到 aid 參數", "error")
            return

        self._aid = aid
        self.btn_load.config(state="disabled")
        self.btn_download.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.title_label.config(text="載入中...")
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(10)
        self.progress_label.config(text="正在取得目錄...")
        self._set_status("正在載入書籍目錄...", "info")

        def _load_worker():
            try:
                soup = fetch_catalog(aid)
                book_name = parse_book_title(soup)
                volumes = parse_volumes(soup)
                self.msg_queue.put(("catalog_done", book_name, volumes))
            except Exception as e:
                self.msg_queue.put(("catalog_error", str(e)))

        threading.Thread(target=_load_worker, daemon=True).start()

    # ---- 下載 ----

    def _on_download(self):
        if not self._volumes:
            return
        selected = [v for v, var in zip(self._volumes, self._check_vars) if var.get()]
        if not selected:
            self._set_status("請至少勾選一卷", "error")
            return
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self.progress_bar.stop()
        self.progress_bar.config(mode="determinate")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(selected)
        self._set_status(f"下載中... 共 {len(selected)} 卷", "info")

        output_dir = self._path_var.get()
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, selected, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay),
            daemon=True,
        ).start()

    def _on_retry(self):
        if not self._fail_volumes:
            return
        vols = list(self._fail_volumes)
        self._fail_volumes = []
        self.btn_retry.config(state="disabled", text="重試失敗")
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"\n── 重試 {len(vols)} 卷 ──\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(vols)
        self._set_status(f"重試中... 共 {len(vols)} 卷", "info")
        output_dir = self._path_var.get()
        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay),
            daemon=True,
        ).start()

    # ---- Queue 輪詢 ----

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]

                if kind == "catalog_done":
                    _, book_name, volumes = msg
                    self._book_name = book_name
                    self._volumes = volumes
                    self.title_label.config(
                        text=f"書名：{book_name}　共 {len(volumes)} 卷"
                    )
                    self._build_checkbox_list(volumes)
                    self.progress_bar.stop()
                    self.progress_bar.config(mode="determinate")
                    self.progress_label.config(text="載入完成，勾選要下載的卷後按「下載選取」")
                    self.btn_load.config(state="normal")
                    self.btn_download.config(state="normal")
                    self.btn_select_all.config(state="normal")
                    self.btn_deselect_all.config(state="normal")
                    self._set_status(
                        f"已載入：{book_name}，共 {len(volumes)} 卷", "success"
                    )

                elif kind == "catalog_error":
                    _, err = msg
                    self.progress_bar.stop()
                    self.progress_bar.config(mode="determinate")
                    self.title_label.config(text="載入失敗")
                    self.progress_label.config(text="載入失敗，請確認網址")
                    self.btn_load.config(state="normal")
                    self.btn_select_all.config(state="disabled")
                    self.btn_deselect_all.config(state="disabled")
                    hint = "（403 錯誤：網站拒絕存取，可稍後再試）" if "403" in err else ""
                    self._set_status(f"載入失敗：{err}{hint}", "error")

                elif kind == "progress":
                    _, current, total, vol_name = msg
                    self.progress_bar["value"] = current
                    self.progress_bar["maximum"] = total
                    self.progress_label.config(
                        text=f"正在下載 {current:02d}/{total}：{vol_name}"
                    )

                elif kind == "log":
                    _, status, index_str, vol_name, detail = msg
                    icon = "✅" if status == "ok" else "❌"
                    line = f"{icon} {index_str} {vol_name}"
                    if detail:
                        line += f"（{detail}）"
                    self.log_text.config(state="normal")
                    self.log_text.insert("end", line + "\n")
                    self.log_text.see("end")
                    self.log_text.config(state="disabled")

                elif kind == "done":
                    _, success_count, fail_volumes = msg
                    fail_count = len(fail_volumes)
                    total = success_count + fail_count
                    self._fail_volumes = fail_volumes
                    self.btn_load.config(state="normal")
                    self.btn_download.config(state="normal")
                    self.btn_select_all.config(state="normal")
                    self.btn_deselect_all.config(state="normal")
                    if fail_count:
                        self.btn_retry.config(
                            state="normal", text=f"重試 {fail_count} 卷失敗"
                        )
                    else:
                        self.btn_retry.config(state="disabled", text="重試失敗")
                    self.progress_bar["value"] = total
                    self.progress_label.config(text=f"完成 {success_count}/{total} 卷")
                    if fail_volumes:
                        level = "error"
                        names = ", ".join(v["name"] for v in fail_volumes)
                        suffix = f"，失敗：{names}"
                    else:
                        level = "success"
                        suffix = ""
                    self._set_status(f"下載完成 {success_count}/{total}{suffix}", level)

                elif kind == "conv_log":
                    _, ok, filename, detail = msg
                    icon = "✅" if ok else "❌"
                    line = f"{icon} {filename}"
                    if detail:
                        line += f"（{detail}）"
                    self._conv_log.config(state="normal")
                    self._conv_log.insert("end", line + "\n")
                    self._conv_log.see("end")
                    self._conv_log.config(state="disabled")

                elif kind == "conv_done":
                    _, success, fail = msg
                    self._conv_btn.config(
                        state="normal" if self._conv_files else "disabled"
                    )
                    total = success + fail
                    level = "success" if fail == 0 else "error"
                    self._set_status(f"轉換完成 {success}/{total}", level)

                elif kind == "status":
                    smsg, level = msg[1]
                    colors = {"info": "gray", "success": "#2E7D32", "error": "#C62828"}
                    self._status_bar.config(
                        text=smsg, foreground=colors.get(level, "gray")
                    )

        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


def main():
    show_cth_banner()
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.update()
    root.attributes("-topmost", False)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
