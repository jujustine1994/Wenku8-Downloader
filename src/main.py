import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

from src import i18n
from src.i18n import t
from src.config import OUTPUT_DIR, RETRY_COUNT, RETRY_DELAY, REQUEST_INTERVAL
from src import manifest
from src.scraper import (
    parse_aid_from_url, parse_vid_from_url, parse_cid_from_url,
    find_volume_by_cid, fetch_catalog, parse_book_title, parse_volumes,
    assign_categories_and_sequence, resequence_by_category, format_index_token,
    classify_volume,
)
from src.downloader import (
    run_download_all, run_repair_all, scan_existing_volumes, build_filepath,
)
from src.logutil import _write_log, _extract_status
from src.logtext import log_t
from src.sitedata import DEFAULT_SIDE_KEYWORDS, SIDE_INDEX_PREFIX

# 高 DPI 感知（4K/2K 螢幕不模糊，需在 Tk() 前呼叫）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SCRIPT_DIR, ".tool_config.json")

# language 預設是**空字串**，不是 "zh_tw"：填 "zh_tw" 就分不出「使用者選了
# 繁中」和「使用者沒選過」，首次啟動的語言視窗就不知道該不該跳。
DEFAULT_CONFIG = {"language": ""}


def load_config() -> dict:
    """讀 .tool_config.json。檔案不存在或壞掉都回預設值，不讓主程式起不來。"""
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return cfg


def save_config(data: dict) -> None:
    """把 data 合併進設定檔。存不進去就算了——設定寫不了不該讓主程式掛掉。"""
    try:
        cfg = load_config()
        cfg.update(data)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def resolve_output_dir(config: dict, project_root: str) -> str:
    raw = config.get("output_dir", "").strip()
    if raw:
        return raw
    return os.path.join(project_root, OUTPUT_DIR)


def describe_url(url: str) -> tuple[str, str]:
    """把使用者貼的網址翻成一行說明，回傳 (文字, 級別)。

    級別是 "info" / "error"，顏色由呼叫端決定——這裡不碰 widget，才測得動。
    判斷邏輯完全沿用 scraper 那三個現成的純函式，不另外寫一套解析，
    否則提示講的跟實際載入的會漸漸對不上。
    """
    url = url.strip()
    if not url:
        return "", "info"
    try:
        aid = parse_aid_from_url(url)
    except ValueError:
        return "▸ 認不出這個網址，請貼書籍目錄頁或單卷網址", "error"

    vid = parse_vid_from_url(url)
    if vid is not None:
        return f"▸ 單卷 · 書號 {aid} · vid {vid}", "info"

    cid = parse_cid_from_url(url)
    if cid is not None:
        return f"▸ 單卷 · 書號 {aid} · 章節 {cid}（載入後確認是哪一卷）", "info"

    return f"▸ 整套目錄 · 書號 {aid}", "info"


def format_seq_ranges(indexes: list[int], max_parts: int = 3,
                      with_count: bool = True) -> str:
    """把卷序整理成人看得懂的短字串：[1,2,3,5] → "1–3、5（共 4 卷）"。

    連續段落收成區間，段數超過 max_parts 就截斷成「前幾段 等 N 卷」——50 卷
    不連續時全列出來狀態列會爆掉。空清單回空字串，呼叫端自己決定要不要顯示。

    純函式，不查 i18n：這是數字排版，四種語言長得一樣。
    """
    nums = sorted(set(i for i in indexes if isinstance(i, int)))
    if not nums:
        return ""
    spans: list[tuple[int, int]] = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        spans.append((start, prev))
        start = prev = n
    spans.append((start, prev))

    parts = [f"{a}–{b}" if a != b else str(a) for a, b in spans[:max_parts]]
    text = "、".join(parts)
    if len(spans) > max_parts:
        return f"{text} 等" if not with_count else f"{text} 等 {len(nums)} 卷"
    return text if not with_count else f"{text}（共 {len(nums)} 卷）"


def format_volume_summary(volumes: list[dict]) -> str:
    """把一組卷整理成「正式卷 1–8、外傳 1–2（共 10 卷）」。

    ⚠ **不能**把所有 seq_index 丟進 format_seq_ranges 一次算完：正式卷與外傳卷
    是各自獨立編號的，兩邊的 1、2 是不同的卷。混在一起會被 set() 去重——實測
    10 個檔案（正式 1–8＋外傳 1–2）會顯示成「共 8 卷」，數字直接對不上。

    總數一律用實際卷數，不用區間裡的數字推算。
    """
    def seqs(cat_match):
        return [v.get("seq_index", v.get("index", 0)) for v in volumes
                if (v.get("category") == "side") is cat_match]

    parts = []
    main_seqs, side_seqs = seqs(False), seqs(True)
    if main_seqs:
        parts.append("正式卷 " + format_seq_ranges(main_seqs, with_count=False))
    if side_seqs:
        parts.append(f"{SIDE_INDEX_PREFIX} "
                     + format_seq_ranges(side_seqs, with_count=False))
    if not parts:
        return ""
    return "、".join(parts) + f"（共 {len(volumes)} 卷）"

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
        self._recovery_volumes: list = []
        self._conv_files: list[str] = []
        self._aid = None
        self._book_name = None
        # 使用者貼的是單卷網址時鎖定的 vid。None = 整套目錄（既有行為）
        self._single_vid: int | None = None
        # 貼章節頁網址時取到的 cid，目錄回來後反查屬於哪一卷
        self._single_cid: int | None = None
        # 使用者當初貼的網址，會記進 manifest 的 source_url
        self._source_url: str = ""
        # 整份目錄（含未帶進下載清單的卷）。單卷模式下 _volumes 只有一卷，
        # 但「更新」要跟整份目錄比對，兩者不能混用。
        self._catalog_volumes: list = []
        self._updating = False
        _cfg = self._load_config()
        # 語言必須在建任何 widget 之前設好——t() 是建置時查一次表，
        # 設晚了介面會停在預設語言。
        i18n.set_lang(_cfg.get("language"))
        self._lang_saved_code = i18n.get_lang()
        self._current_theme = _cfg.get("theme", "light")
        self._path_var = tk.StringVar()
        self._retry_count = int(_cfg.get("retry_count", RETRY_COUNT))
        self._retry_delay = int(_cfg.get("retry_delay", RETRY_DELAY))
        # 送出間隔：對付 wenku8 的 HTTP 429 限流，見 src/ratelimit.py
        self._request_interval = float(_cfg.get("request_interval", REQUEST_INTERVAL))
        self._fname_index = _cfg.get("filename_index", "padded")
        self._fname_book_name = bool(_cfg.get("filename_book_name", True))
        self._fname_separator = _cfg.get("filename_separator", " ")
        self._convert_traditional = bool(_cfg.get("convert_traditional", True))
        self._side_keywords: list[str] = _cfg.get("side_keywords", list(DEFAULT_SIDE_KEYWORDS))
        self._last_batch_vids: set = set()
        self._repair_mode = False
        self._auto_repair_active = False
        self._auto_round = 0
        self._skip_event = threading.Event()
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
        frame_url = ttk.LabelFrame(
            tab_download, text=" 書籍網址（整套目錄或單卷皆可） ", padding=8
        )
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
        ttk.Button(url_row, text="⚙", command=self._goto_settings_tab, width=4).grid(
            row=0, column=2, padx=(4, 0)
        )

        # 貼進去的當下就告訴使用者程式會怎麼處理這條網址（整套 / 單卷 / 認不出），
        # 不用等按了「載入」抓完目錄才從 Preview 視窗標題發現。
        self._url_hint = ttk.Label(frame_url, text="", font=FH, foreground="gray")
        self._url_hint.pack(fill="x", anchor="w", pady=(4, 0))
        self.url_var.trace_add("write", lambda *_: self._update_url_hint())

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
        self._enable_wheel_scroll(self._check_canvas)

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
        # 「更新」會重抓目錄（連網），跟純本地的「掃描既有檔案」刻意分開兩顆按鈕：
        # 併在一起使用者會不知道按下去到底會不會連網。
        self.btn_update = ttk.Button(
            btn_row, text="更新", command=self._on_update, width=8, state="disabled"
        )
        self.btn_update.pack(side="right", ipady=4, padx=(0, 6))
        self.btn_recover = ttk.Button(
            btn_row, text="重試/修復", command=self._on_recover, width=10, state="disabled"
        )
        self.btn_recover.pack(side="right", ipady=4, padx=(0, 6))
        self.btn_scan = ttk.Button(
            btn_row, text="掃描既有檔案", command=self._on_scan, width=12, state="disabled"
        )
        self.btn_scan.pack(side="right", ipady=4, padx=(0, 6))
        self.btn_manage = ttk.Button(
            btn_row, text="管理", command=self._manage_recovery_dialog, width=5, state="disabled"
        )
        self.btn_manage.pack(side="right", ipady=4, padx=(0, 2))
        self.btn_skip = ttk.Button(
            btn_row, text="跳過目前卷", command=self._on_skip, width=10, state="disabled"
        )
        self.btn_skip.pack(side="right", ipady=4, padx=(0, 6))

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

        self._tab_settings = ttk.Frame(self._notebook)
        self._notebook.add(self._tab_settings, text="  設定  ")
        self._build_settings_tab(self._tab_settings)

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
        tab.rowconfigure(2, weight=1)
        tab.rowconfigure(4, weight=1)

        ttk.Label(
            tab, text="把已下載的 TXT 檔案批次轉換成台灣繁體中文（簡轉繁），不需要重新下載。",
            font=FH, foreground="gray"
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))

        # Header：計數 + 選擇檔案按鈕
        frame_header = ttk.Frame(tab)
        frame_header.grid(row=1, column=0, sticky="ew", **pad)
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
        frame_files.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 6))
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
        self._enable_wheel_scroll(self._conv_canvas)

        # 輸出模式 + 開始按鈕
        frame_output = ttk.Frame(tab)
        frame_output.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 6))

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
        frame_conv_log.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 6))
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

    def _ensure_output_dir(self) -> str | None:
        """驗證下載路徑可用；不可用時顯示錯誤並回傳 None，避免背景執行緒卡死。"""
        path = self._path_var.get().strip()
        if not path:
            self._set_status("下載路徑不能為空，請先設定「下載至」", "error")
            return None
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            self._set_status(f"下載路徑無法使用：{path}（{e}）", "error")
            return None
        return path

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

    # ⚠ sv-ttk 已知效能問題：用 sprite-sheet 圖片裁切畫元件（非原生繪製）。
    # 本專案卷列表、轉換檔案清單、識別關鍵字清單都會動態大量建立/銷毀 widget，
    # 每次操作會在 Tcl 端觸發明顯卡頓，跟 Python 端邏輯無關。停用後卡頓消失。
    # 詳見 C:\Users\CTH\.claude\project-rules\windows-tool\tkinter-ui\INDEX.md
    USE_SV_TTK = False

    def _apply_theme(self, theme_key: str):
        theme = THEMES.get(theme_key, THEMES["light"])
        if self.USE_SV_TTK:
            try:
                import sv_ttk
                sv_ttk.set_theme(theme["sv"])
            except ImportError:
                pass

        from tkinter import font as tkfont
        for fname in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            tkfont.nametofont(fname).configure(family="Microsoft JhengHei", size=12)

        style = ttk.Style()
        style.configure("TButton", font=F)
        style.configure("TEntry", font=F)
        style.configure("TCombobox", font=F)
        style.configure("TNotebook.Tab", font=FB, padding=(20, 10))
        style.configure("TLabelframe.Label", font=F, foreground=theme["frame_title"])
        label_fg = theme["label_fg"]
        for w in ("TLabel", "TCheckbutton", "TRadiobutton"):
            kw = {"font": F}
            if label_fg:
                kw["foreground"] = label_fg
            style.configure(w, **kw)

        self.log_text.config(bg=theme["log_bg"], fg=theme["log_fg"],
                             insertbackground=theme["log_fg"])
        self._conv_log.config(bg=theme["log_bg"], fg=theme["log_fg"],
                              insertbackground=theme["log_fg"])
        self._current_theme = theme_key

    # ---- 設定 tab ----

    def _goto_settings_tab(self):
        self._notebook.select(self._tab_settings)

    def _build_settings_tab(self, tab: ttk.Frame):
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=0)
        tab.rowconfigure(0, weight=1)

        canvas = tk.Canvas(tab, highlightthickness=0)
        vsb = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew", padx=(14, 0), pady=(12, 0))
        vsb.grid(row=0, column=1, sticky="ns", pady=(12, 0))
        self._enable_wheel_scroll(canvas)

        content = ttk.Frame(canvas, padding=(0, 0, 14, 12))
        content_win = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(content_win, width=e.width),
        )

        # ===== 語言 =====
        # 標籤固定英文，選項用各語言自己的說法——任何語言下都認得出來。
        # 選項由 i18n.LANGUAGES 動態生成，新增語言時這裡一個字都不必改。
        lang_row = ttk.Frame(content)
        lang_row.pack(fill="x", pady=(0, 6))
        ttk.Label(lang_row, text="Language:", font=FB).pack(side="left", padx=(0, 8))
        self._lang_choices = i18n.available_languages()
        # ⚠ 讀 config 不讀 i18n.get_lang()：使用者選了新語言但按「稍後」不重啟時，
        # runtime 語言還是舊的，用 runtime 值當基準會把他的選擇默默寫回去。
        _saved = self._load_config().get("language", "")
        self._lang_saved_code = _saved if i18n.is_supported(_saved) else i18n.DEFAULT_LANG
        _names = [name for _, name in self._lang_choices]
        _current = next((n for c, n in self._lang_choices
                         if c == self._lang_saved_code), _names[0])
        self._lang_var = tk.StringVar(value=_current)
        self._lang_combo = ttk.Combobox(
            lang_row, textvariable=self._lang_var, values=_names,
            width=14, state="readonly", font=F
        )
        self._lang_combo.pack(side="left")

        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=16)

        # ===== 外觀 =====
        ttk.Label(content, text=t("gui.settings.appearance"), font=FB).pack(
            anchor="w", pady=(0, 6)
        )
        appearance_row = ttk.Frame(content)
        appearance_row.pack(fill="x")
        self._theme_summary_label = ttk.Label(
            appearance_row, text=self._theme_summary_text(), font=F, foreground="gray"
        )
        self._theme_summary_label.pack(side="left")
        ttk.Button(
            appearance_row, text="外觀設定...", command=self._open_appearance_dialog, width=14
        ).pack(side="right", ipady=4)

        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=16)

        # ===== 下載 =====
        ttk.Label(content, text="下載", font=FB).pack(anchor="w", pady=(0, 8))

        row1 = ttk.Frame(content)
        row1.pack(fill="x", pady=(0, 6))
        ttk.Label(row1, text="重試次數：", font=F).pack(side="left")
        retry_infinite = self._retry_count <= 0
        self._retry_count_var = tk.IntVar(value=self._retry_count if not retry_infinite else 3)
        self._retry_count_spin = ttk.Spinbox(
            row1, from_=1, to=10, textvariable=self._retry_count_var,
            width=5, font=F
        )
        self._retry_count_spin.pack(side="left", padx=(8, 4))
        ttk.Label(row1, text="次", font=F).pack(side="left")

        row1b = ttk.Frame(content)
        row1b.pack(fill="x", pady=(0, 12))
        self._retry_infinite_var = tk.BooleanVar(value=retry_infinite)

        def _on_infinite_toggle(*_):
            self._retry_count_spin.config(
                state="disabled" if self._retry_infinite_var.get() else "normal"
            )

        self._on_infinite_toggle = _on_infinite_toggle
        ttk.Checkbutton(
            row1b, text="無限重試（直到成功或手動跳過）",
            variable=self._retry_infinite_var, command=_on_infinite_toggle
        ).pack(side="left")
        _on_infinite_toggle()

        row2 = ttk.Frame(content)
        row2.pack(fill="x")
        ttk.Label(row2, text="重試間隔：", font=F).pack(side="left")
        self._retry_delay_var = tk.IntVar(value=self._retry_delay)
        ttk.Spinbox(
            row2, from_=1, to=30, textvariable=self._retry_delay_var,
            width=5, font=F
        ).pack(side="left", padx=(8, 4))
        ttk.Label(row2, text="秒", font=F).pack(side="left")

        row2b = ttk.Frame(content)
        row2b.pack(fill="x", pady=(8, 0))
        ttk.Label(row2b, text="送出間隔：", font=F).pack(side="left")
        self._request_interval_var = tk.DoubleVar(value=self._request_interval)
        ttk.Spinbox(
            row2b, from_=0, to=30, increment=0.5,
            textvariable=self._request_interval_var, width=5, font=F
        ).pack(side="left", padx=(8, 4))
        ttk.Label(
            row2b,
            text="秒（每次連線之間至少等這麼久，調大可減少被網站限流）",
            font=FH,
        ).pack(side="left")

        row3 = ttk.Frame(content)
        row3.pack(fill="x", pady=(12, 0))
        self._convert_traditional_var = tk.BooleanVar(value=self._convert_traditional)
        ttk.Checkbutton(
            row3, text="下載後自動簡轉繁（關閉則保留原始簡體）",
            variable=self._convert_traditional_var
        ).pack(side="left")

        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=16)

        # ===== 命名 =====
        ttk.Label(content, text="命名", font=FB).pack(anchor="w", pady=(0, 8))

        ttk.Label(content, text="序號格式", font=FB).pack(anchor="w", pady=(0, 6))
        self._fname_index_var = tk.StringVar(value=self._fname_index)
        for val, label in [("padded", "零補位（01, 02…）"),
                            ("plain",  "純數字（1, 2…）"),
                            ("none",   "不顯示")]:
            ttk.Radiobutton(
                content, text=label,
                variable=self._fname_index_var, value=val
            ).pack(anchor="w", pady=2)

        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=10)

        # 書名開關
        self._fname_book_var = tk.BooleanVar(value=self._fname_book_name)
        ttk.Checkbutton(
            content, text="檔名含書名", variable=self._fname_book_var
        ).pack(anchor="w")

        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=10)

        # 分隔符號
        sep_row = ttk.Frame(content)
        sep_row.pack(anchor="w")
        ttk.Label(sep_row, text="分隔符號：", font=F).pack(side="left")
        self._fname_sep_var = tk.StringVar(value=self._fname_separator)
        ttk.Entry(sep_row, textvariable=self._fname_sep_var, width=5, font=FM).pack(side="left")
        ttk.Label(sep_row, text="（空白 = 空格）", font=FH, foreground="gray").pack(
            side="left", padx=(6, 0)
        )

        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=10)

        # 即時預覽
        naming_preview_label = ttk.Label(content, text="", font=FM)
        naming_preview_label.pack(anchor="w")

        def _update_naming_preview(*_):
            idx = self._fname_index_var.get()
            book = self._fname_book_var.get()
            sep = self._fname_sep_var.get() or " "
            parts = []
            if idx == "padded":
                parts.append("01")
            elif idx == "plain":
                parts.append("1")
            if book:
                parts.append("書名")
            parts.append("第一卷")
            naming_preview_label.config(text="預覽：" + sep.join(parts) + ".txt")

        self._fname_index_var.trace_add("write", _update_naming_preview)
        self._fname_book_var.trace_add("write", _update_naming_preview)
        self._fname_sep_var.trace_add("write", _update_naming_preview)
        _update_naming_preview()

        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=16)

        # ===== 識別 =====
        ttk.Label(content, text="識別（外傳關鍵字）", font=FB).pack(anchor="w", pady=(0, 6))
        identify_row = ttk.Frame(content)
        identify_row.pack(fill="x")
        self._kw_summary_label = ttk.Label(
            identify_row, text=self._kw_summary_text(), font=F, foreground="gray"
        )
        self._kw_summary_label.pack(side="left")
        ttk.Button(
            identify_row, text="識別設定...", command=self._open_identify_dialog, width=14
        ).pack(side="right", ipady=4)

        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=16)

        # ===== 版本更新 =====
        self._build_update_section(content)

        # ===== 套用 / 取消（固定在底部，不隨內容捲動）=====
        btn_row = ttk.Frame(tab)
        btn_row.grid(row=1, column=0, columnspan=2, pady=(8, 12))
        ttk.Button(btn_row, text="套用", command=self._apply_settings, width=10).pack(
            side="left", padx=4, ipady=4
        )
        ttk.Button(btn_row, text="取消", command=self._reset_settings_fields, width=10).pack(
            side="left", padx=4, ipady=4
        )

    # ------------------------------------------------------------------
    # 版本更新區塊
    #
    # ⚠ 全程沒有任何一步自動觸發：「檢查更新」只讀不寫；有新版本才會出現
    # 「一鍵安裝」，按下去還要先跳確認框，使用者按確定才真的動檔案。
    # 更新完不自動重啟（跟語言切換不同），只跳訊息框請使用者自己關掉重開，
    # 因為更新可能動到正在執行中的模組，自動重啟的邊界情況不值得為手動
    # 觸發的功能多繞。
    # ------------------------------------------------------------------

    def _build_update_section(self, content: ttk.Frame):
        ttk.Label(content, text=t("gui.settings.update"), font=FB).pack(
            anchor="w", pady=(0, 6)
        )
        update_row = ttk.Frame(content)
        update_row.pack(fill="x")

        self._check_update_btn = ttk.Button(
            update_row, text=t("gui.btn.check_update"),
            command=self._on_check_update, width=14
        )
        self._check_update_btn.pack(side="left", ipady=4)

        self._install_update_btn = ttk.Button(
            update_row, text=t("gui.btn.install_update"),
            command=self._on_install_update, width=14
        )
        # 有新版本才 pack，預設不顯示

        self._update_status_label = ttk.Label(
            content, text="", font=FH, foreground="gray",
            justify="left", anchor="w", wraplength=420,
        )
        self._update_status_label.pack(anchor="w", pady=(6, 0), fill="x")

        self._pending_update_summary = ""

    def _on_check_update(self):
        self._check_update_btn.config(state="disabled")
        self._install_update_btn.pack_forget()
        self._update_status_label.config(text=t("gui.update.checking"))

        def worker():
            from src import update_checker
            result = update_checker.check_for_update()
            try:
                self.root.after(0, self._on_check_update_done, result)
            except (RuntimeError, tk.TclError):
                pass  # 視窗已關閉，結果沒人要了

        threading.Thread(target=worker, daemon=True).start()

    def _on_check_update_done(self, result: dict):
        self._check_update_btn.config(state="normal")
        status = result.get("status")

        if status == "no_git":
            self._update_status_label.config(text=t("gui.update.no_git"))
        elif status == "offline":
            self._update_status_label.config(text=t("gui.update.offline"))
        elif status == "dirty":
            self._update_status_label.config(text=t("gui.update.dirty"))
        elif status == "ahead":
            self._update_status_label.config(text=t("gui.update.ahead"))
        elif status == "up_to_date":
            self._update_status_label.config(text=t("gui.update.up_to_date"))
        elif status == "update_available":
            self._pending_update_summary = result.get("summary", "")
            self._update_status_label.config(
                text=t("gui.update.available", count=result.get("commits", 0)))
            self._install_update_btn.pack(side="left", padx=(8, 0), ipady=4)
        else:
            self._update_status_label.config(
                text=t("gui.update.error", msg=result.get("message", status or "")))

    def _on_install_update(self):
        from tkinter import messagebox
        if not messagebox.askyesno(
            t("gui.update.confirm_title"),
            t("gui.update.confirm_body", summary=self._pending_update_summary),
        ):
            return
        self._check_update_btn.config(state="disabled")
        self._install_update_btn.config(state="disabled")
        self._update_status_label.config(text=t("gui.update.installing"))

        def worker():
            from src import update_checker
            result = update_checker.install_update()
            try:
                self.root.after(0, self._on_install_update_done, result)
            except (RuntimeError, tk.TclError):
                pass  # 視窗已關閉，結果沒人要了

        threading.Thread(target=worker, daemon=True).start()

    def _on_install_update_done(self, result: dict):
        from tkinter import messagebox
        self._check_update_btn.config(state="normal")
        status = result.get("status")

        if status == "updated":
            self._install_update_btn.pack_forget()
            self._update_status_label.config(
                text=t("gui.update.updated", commit=result.get("commit", "")))
            messagebox.showinfo(
                t("gui.update.done_title"), t("gui.update.done_body"))
        else:
            self._install_update_btn.config(state="normal")
            self._update_status_label.config(
                text=t("gui.update.error", msg=result.get("message", status or "")))

    def _apply_settings(self):
        """套用「設定」tab 上直接可見的欄位（下載／命名）。外觀、識別各自有獨立彈出視窗即時套用。"""
        self._retry_count = 0 if self._retry_infinite_var.get() else self._retry_count_var.get()
        self._retry_delay = self._retry_delay_var.get()
        self._request_interval = max(0.0, float(self._request_interval_var.get()))
        self._fname_index = self._fname_index_var.get()
        self._fname_book_name = self._fname_book_var.get()
        self._fname_separator = self._fname_sep_var.get() or " "
        self._convert_traditional = self._convert_traditional_var.get()
        new_lang = self._selected_lang_code()
        lang_changed = new_lang != self._lang_saved_code
        self._save_config({
            "retry_count": self._retry_count,
            "retry_delay": self._retry_delay,
            "request_interval": self._request_interval,
            "filename_index": self._fname_index,
            "filename_book_name": self._fname_book_name,
            "filename_separator": self._fname_separator,
            "convert_traditional": self._convert_traditional,
            "language": new_lang,
        })
        self._lang_saved_code = new_lang
        self._set_status("設定已套用", "success")
        # 只有語言真的變更才打擾使用者——改重試次數不該跳重啟視窗
        if lang_changed:
            self._prompt_restart_for_language()

    def _selected_lang_code(self) -> str:
        """把下拉選單顯示的名稱換回代號。取不到就維持原設定，不亂改。"""
        chosen = self._lang_var.get()
        for code, name in self._lang_choices:
            if name == chosen:
                return code
        return self._lang_saved_code

    def _prompt_restart_for_language(self):
        """語言變更後問是否重啟。

        視窗全英文：此刻介面還是舊語言、使用者要的是新語言，用任一方都尷尬，
        英文最中立。
        """
        from tkinter import messagebox
        if messagebox.askyesno(
            "Language Changed",
            "Restart the app to apply the new language.\n\nRestart now?",
        ):
            self._restart_app()

    def _restart_app(self):
        """起一個新行程再關掉自己。

        不用 os.execv：Windows 上它會就地覆寫當前行程，tkinter 還沒釋放的視窗
        handle 可能殘留，看起來像關不掉的殭屍視窗。
        """
        try:
            subprocess.Popen([sys.executable, *sys.argv], close_fds=True)
        except OSError:
            # 起不了新行程就什麼都不做——使用者下次自己開一樣會生效，
            # 這裡把舊視窗關掉反而讓人以為程式壞了
            return
        self.root.destroy()

    def _reset_settings_fields(self):
        """取消：把設定 tab 上的欄位還原成目前實際生效的值（未套用的修改會被丟棄）。"""
        retry_infinite = self._retry_count <= 0
        self._retry_count_var.set(self._retry_count if not retry_infinite else 3)
        self._retry_infinite_var.set(retry_infinite)
        self._on_infinite_toggle()
        self._retry_delay_var.set(self._retry_delay)
        self._request_interval_var.set(self._request_interval)
        self._fname_index_var.set(self._fname_index)
        self._fname_book_var.set(self._fname_book_name)
        self._fname_sep_var.set(self._fname_separator)
        self._lang_var.set(next((n for c, n in self._lang_choices
                                 if c == self._lang_saved_code),
                                self._lang_choices[0][1]))

    # ---- 外觀設定（彈出視窗）----

    def _theme_summary_text(self) -> str:
        return f"目前主題：{THEMES.get(self._current_theme, THEMES['light'])['name']}"

    def _kw_summary_text(self) -> str:
        return f"目前共 {len(self._side_keywords)} 個關鍵字"

    def _open_appearance_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("外觀設定")
        win.resizable(True, True)
        win.minsize(420, 340)
        win.grab_set()

        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        left.pack(side="left", anchor="n", padx=(0, 16))
        right = ttk.Frame(body)
        right.pack(side="left", anchor="n")

        ttk.Label(left, text="配色主題").pack(anchor="w", pady=(0, 10))
        theme_var = tk.StringVar(value=self._current_theme)
        for key, info in THEMES.items():
            ttk.Radiobutton(
                left, text=info["name"], variable=theme_var, value=key
            ).pack(anchor="w", pady=4)

        # 固定比例放大原本 210x168 的預覽尺寸（不隨視窗縮放，避免字體比例跑掉）
        S = 1.6
        PW, PH = round(210 * S), round(168 * S)
        preview = tk.Canvas(right, width=PW, height=PH, highlightthickness=1,
                            highlightbackground="#CCCCCC")
        preview.pack()
        ttk.Label(right, text="預覽", foreground="gray").pack(pady=(4, 0))

        def draw_preview(key):
            theme = THEMES.get(key, THEMES["light"])
            c = preview
            c.delete("all")
            v = lambda n: round(n * S)
            fs = round(7 * S)
            c.create_rectangle(0, 0, PW, PH, fill=theme["win_bg"], outline="")
            tbar_bg = theme["card_bg"] if theme["sv"] == "light" else "#2D2D2D"
            c.create_rectangle(0, 0, PW, v(22), fill=tbar_bg, outline="")
            c.create_text(v(10), v(11), text="Wenku8 Downloader", anchor="w",
                          fill=theme["frame_title"], font=("Microsoft JhengHei", fs, "bold"))
            c.create_rectangle(v(8), v(28), PW - v(8), v(68),
                               fill=theme["card_bg"], outline=theme["border"])
            c.create_text(v(16), v(33), text=" 書籍目錄網址 ", anchor="w",
                          fill=theme["frame_title"], font=("Microsoft JhengHei", fs, "bold"))
            c.create_rectangle(v(16), v(44), PW - v(16), v(58),
                               fill=theme["log_bg"], outline=theme["border"])
            bx1, bx2 = v(65), v(145)
            c.create_rectangle(bx1, v(74), bx2, v(88), fill=theme["btn_bg"], outline="")
            c.create_text((bx1 + bx2) / 2, v(81), text="下載全部",
                          fill=theme["btn_fg"], font=("Microsoft JhengHei", fs))
            c.create_rectangle(v(8), v(94), PW - v(8), PH - v(6),
                               fill=theme["card_bg"], outline=theme["border"])
            c.create_text(v(16), v(99), text=" 進度 ", anchor="w",
                          fill=theme["frame_title"], font=("Microsoft JhengHei", fs, "bold"))
            bar_bg = "#E5E5E5" if theme["sv"] == "light" else "#3A3A3A"
            c.create_rectangle(v(16), v(110), PW - v(16), v(116), fill=bar_bg, outline="")
            c.create_rectangle(v(16), v(110), v(70), v(116), fill=theme["pbar"], outline="")
            c.create_rectangle(v(16), v(122), PW - v(16), PH - v(12),
                               fill=theme["log_bg"], outline=theme["border"])
            c.create_text(v(20), v(128), text="等待中...", anchor="nw", fill=theme["log_fg"],
                          font=("Microsoft JhengHei", fs))

        theme_var.trace_add("write", lambda *_: draw_preview(theme_var.get()))
        draw_preview(self._current_theme)

        def _apply():
            self._apply_theme(theme_var.get())
            self._save_config({"theme": theme_var.get()})
            self._theme_summary_label.config(text=self._theme_summary_text())
            win.destroy()

        btn_row = ttk.Frame(win)
        btn_row.pack(pady=(4, 16))
        ttk.Button(btn_row, text="套用", command=_apply, width=10).pack(
            side="left", padx=4, ipady=4
        )
        ttk.Button(btn_row, text="取消", command=win.destroy, width=10).pack(
            side="left", padx=4, ipady=4
        )

    # ---- 識別設定（彈出視窗）----

    def _open_identify_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("識別設定（外傳關鍵字）")
        win.resizable(True, True)
        win.geometry("440x560")
        win.minsize(360, 360)
        win.grab_set()

        body = ttk.Frame(win, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        ttk.Label(body, text="外傳關鍵字", font=FB).grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )

        id_list_frame = ttk.Frame(body)
        id_list_frame.grid(row=1, column=0, sticky="nsew")
        id_list_frame.columnconfigure(0, weight=1)
        id_list_frame.rowconfigure(0, weight=1)

        id_canvas = tk.Canvas(id_list_frame, highlightthickness=0)
        id_sb = ttk.Scrollbar(id_list_frame, orient="vertical", command=id_canvas.yview)
        id_canvas.configure(yscrollcommand=id_sb.set)
        id_canvas.grid(row=0, column=0, sticky="nsew")
        id_sb.grid(row=0, column=1, sticky="ns")
        self._bind_wheel_to_dialog(win, id_canvas)

        id_kw_frame = ttk.Frame(id_canvas)
        id_kw_win = id_canvas.create_window((0, 0), window=id_kw_frame, anchor="nw")
        id_kw_frame.bind(
            "<Configure>",
            lambda e: id_canvas.configure(scrollregion=id_canvas.bbox("all")),
        )
        id_canvas.bind(
            "<Configure>",
            lambda e: id_canvas.itemconfig(id_kw_win, width=e.width),
        )

        kw_list = list(self._side_keywords)

        def _refresh_kw_list():
            for w in id_kw_frame.winfo_children():
                w.destroy()
            for kw in kw_list:
                row = ttk.Frame(id_kw_frame)
                row.pack(fill="x", padx=4, pady=1)
                row.columnconfigure(0, weight=1)
                ttk.Label(row, text=kw, font=F, anchor="w").grid(
                    row=0, column=0, sticky="ew"
                )
                ttk.Button(
                    row, text="刪除", width=5,
                    command=lambda k=kw: _delete_kw(k),
                ).grid(row=0, column=1, padx=(4, 0))

        def _delete_kw(kw):
            if kw in kw_list:
                kw_list.remove(kw)
                _refresh_kw_list()

        add_row = ttk.Frame(body)
        add_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        add_row.columnconfigure(0, weight=1)
        new_kw_var = tk.StringVar()
        new_kw_entry = ttk.Entry(add_row, textvariable=new_kw_var, font=F)
        new_kw_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        def _add_kw(*_):
            kw = new_kw_var.get().strip()
            if kw and kw not in kw_list:
                kw_list.append(kw)
                new_kw_var.set("")
                _refresh_kw_list()
                id_canvas.yview_moveto(1.0)

        new_kw_entry.bind("<Return>", _add_kw)
        ttk.Button(add_row, text="新增", width=6, command=_add_kw).grid(row=0, column=1)

        _refresh_kw_list()

        def _apply():
            self._side_keywords = list(kw_list)
            self._save_config({"side_keywords": self._side_keywords})
            win.destroy()

        btn_row = ttk.Frame(win)
        btn_row.pack(pady=(0, 16))
        ttk.Button(btn_row, text="套用", command=_apply, width=10).pack(
            side="left", padx=4, ipady=4
        )
        ttk.Button(btn_row, text="取消", command=win.destroy, width=10).pack(
            side="left", padx=4, ipady=4
        )

    # ---- 設定檔 ----

    def _load_config(self) -> dict:
        return load_config()

    def _save_config(self, data: dict):
        save_config(data)

    # ---- 勾選清單 ----

    def _build_checkbox_list(self, volumes: list[dict]):
        for w in self._cb_frame.winfo_children():
            w.destroy()
        self._check_vars = []
        for v in volumes:
            var = tk.BooleanVar(value=True)
            self._check_vars.append(var)
            seq_index = v.get("seq_index", v["index"])
            seq_total = v.get("seq_total", len(volumes))
            # 這個標籤刻意跟檔名用同一個前綴／編號組法，讓使用者在清單上看到的
            # 就是待會兒存出來的檔名開頭。所以它是資料，不翻譯。
            prefix = SIDE_INDEX_PREFIX if v.get("category") == "side" else ""
            label = format_index_token(seq_index, seq_total, "padded", prefix)
            cb = ttk.Checkbutton(
                self._cb_frame,
                text=f"  {label}  {v['name']}",
                variable=var,
            )
            cb.pack(anchor="w", fill="x", padx=4, pady=1)
        self._check_canvas.yview_moveto(0)

    def _reset_book_state(self):
        """清空跟目前這本書相關的狀態：卷列表、待處理清單與對應按鈕。
        載入新書、或 Preview 視窗取消時共用，避免舊書的清單/按鈕狀態殘留到下一本書。"""
        self._recovery_volumes = []
        self._auto_repair_active = False
        self._auto_round = 0
        self._build_checkbox_list([])
        self.btn_download.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
        self.btn_scan.config(state="disabled")
        self.btn_update.config(state="disabled")
        self._single_vid = None
        self._single_cid = None
        self._catalog_volumes = []

    # ---- manifest / 更新 ----

    def _build_path_fn(self, output_dir: str):
        """給 manifest 用的檔名計算函式。

        manifest 不能 import downloader（downloader 會 import manifest 寫紀錄，
        反過來就是循環），所以算檔名一律由這裡包好再傳進去。
        """
        def build_path(vol: dict) -> str:
            seq_index = vol.get("seq_index", vol.get("index", 1))
            seq_total = vol.get("seq_total", len(self._volumes) or 1)
            prefix = SIDE_INDEX_PREFIX if vol.get("category") == "side" else ""
            return build_filepath(
                output_dir, self._book_name, seq_index, vol["name"], seq_total,
                self._fname_index, self._fname_book_name, self._fname_separator,
                index_prefix=prefix,
                convert_traditional=self._convert_traditional,
            )
        return build_path

    def _make_plan(self, volumes: list[dict], output_dir: str) -> dict:
        """比對卷列表 / manifest / 磁碟，回傳 plan_update() 的分組結果。純本地。"""
        build_path = self._build_path_fn(output_dir)
        # 順手把書號與使用者貼的網址記進 manifest：這樣資料夾單獨存在時，
        # 光看 .wenku8.json 就知道是哪本書、從哪裡抓的，不必回頭猜。
        manifest.record_book_meta(output_dir, self._aid, self._book_name,
                                  self._source_url)
        data = manifest.load(output_dir)
        if not data["books"].get(str(self._aid)):
            # 沒有紀錄（第一次用這個版本、或換過資料夾）→ 按檔名回推建一份，不重抓
            data = manifest.rebuild_from_files(
                output_dir, self._aid, self._book_name, volumes, build_path
            )
        book = data["books"].get(str(self._aid), {})
        return manifest.plan_update(
            volumes, book, build_path,
            manifest.script_for(self._convert_traditional),
            manifest.median_chars(data, self._aid),
        )

    def _update_url_hint(self):
        text, level = describe_url(self.url_var.get())
        # 顏色沿用狀態列那組，不另外挑一套；灰色在三個主題下都讀得到
        self._url_hint.config(
            text=text, foreground="#C62828" if level == "error" else "gray"
        )

    def _apply_plan_selection(self, vids: set):
        """照 vid 集合設定下載清單的勾選狀態。"""
        for vol, var in zip(self._volumes, self._check_vars):
            var.set(vol["vid"] in vids)

    PLAN_GROUP_LABELS = {
        "new":              "新卷（目錄有、本機沒有）",
        "incomplete":       "不完整（缺檔或驗證未通過）",
        "changed":          "檔案被改過（大小與紀錄不符）",
        "chapters_changed": "章節有變動（站方補章或重新分卷）",
        "script_mismatch":  "簡繁與目前設定不同",
        "ok":               "已完整（不需處理）",
    }

    def _notify_existing_files(self):
        """載入完成後比對資料夾，已經有檔案就提醒使用者要只補缺的還是全部重抓。

        純本地比對，不重抓目錄——目錄剛剛才抓過。資料夾裡一卷都沒有時什麼都不做，
        維持載入完直接勾選下載的既有行為。
        """
        if not self._volumes:
            return
        output_dir = self._path_var.get().strip()
        if not output_dir or not os.path.isdir(output_dir):
            return
        try:
            plan = self._make_plan(self._volumes, output_dir)
        except OSError as e:
            _write_log(log_t("err.manifest", aid=self._aid, op="scan",
                             etype=type(e).__name__), "ERROR")
            return

        have = plan["ok"] + plan["changed"] + plan["script_mismatch"]
        if not have:
            return

        need = plan["new"] + plan["incomplete"]
        have_text = format_volume_summary(have)
        if not need:
            # 全部都在而且都完整：講一句就好，不必為了「需要下載 0 卷」跳視窗
            self._set_status(
                f"資料夾裡已有 {have_text}，全部完整，沒有需要下載的卷", "success"
            )
            self._select_all(False)
            return
        self._set_status(
            f"資料夾裡已有 {have_text}，需要下載 {len(need)} 卷", "info"
        )

        win = tk.Toplevel(self.root)
        win.title("資料夾裡已有檔案")
        win.resizable(False, False)
        win.grab_set()
        ttk.Label(
            win,
            text=(f"這本書共 {len(self._volumes)} 卷，"
                  f"資料夾裡已有 {have_text}。\n"
                  f"需要下載的有 {len(need)} 卷。"),
            font=F, justify="left",
        ).pack(anchor="w", padx=16, pady=(16, 10))

        def _only_missing():
            self._apply_plan_selection({v["vid"] for v in need})
            win.destroy()

        def _redownload_all():
            self._apply_plan_selection({v["vid"] for v in self._volumes})
            win.destroy()

        row = ttk.Frame(win)
        row.pack(padx=16, pady=(0, 16))
        ttk.Button(row, text="只抓缺的與新的", command=_only_missing,
                   width=16).pack(side="left", padx=4, ipady=4)
        ttk.Button(row, text="全部重抓覆蓋", command=_redownload_all,
                   width=14).pack(side="left", padx=4, ipady=4)
        win.protocol("WM_DELETE_WINDOW", _only_missing)

    def _on_update(self):
        """重抓目錄 → 跟 manifest／磁碟比對 → 跳確認視窗讓使用者挑要下載哪些。"""
        if not self._aid or self._updating:
            return
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            return
        self._updating = True
        self.btn_update.config(state="disabled")
        self.btn_load.config(state="disabled")
        self._set_status("正在比對目錄與資料夾...", "info")
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(10)

        aid = self._aid
        keywords = list(self._side_keywords)
        # 使用者在 Preview 手動調過的分類不能被重新分類蓋掉，只有新卷才跑關鍵字
        known = {v["vid"]: v["category"] for v in (self._catalog_volumes or self._volumes)}

        def _worker():
            try:
                soup = fetch_catalog(aid)
                book_name = parse_book_title(soup)
                volumes = parse_volumes(soup)
                classified = [
                    {**v, "category": known.get(v["vid"])
                     or classify_volume(v["name"], keywords)}
                    for v in volumes
                ]
                self.msg_queue.put(
                    ("update_catalog", book_name, resequence_by_category(classified))
                )
            except Exception as e:
                self.msg_queue.put(
                    ("catalog_error", str(e), type(e).__name__, _extract_status(e))
                )

        threading.Thread(target=_worker, daemon=True).start()

    def _open_update_dialog(self, plan: dict, total: int):
        """更新結果的確認視窗：六組分開列，使用者勾完直接送進既有下載流程。"""
        win = tk.Toplevel(self.root)
        win.title(f"更新 - {self._book_name}")
        win.resizable(True, True)
        win.geometry("520x560")
        win.minsize(400, 320)
        win.grab_set()

        need_count = sum(len(plan[g]) for g in manifest.PLAN_DEFAULT_CHECKED)
        ttk.Label(
            win, text=f"共 {total} 卷，建議下載 {need_count} 卷", font=FB
        ).pack(anchor="w", padx=12, pady=(12, 6))

        outer = ttk.Frame(win)
        outer.pack(fill="both", expand=True, padx=12)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self._bind_wheel_to_dialog(win, canvas)
        body = ttk.Frame(canvas)
        body_win = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(body_win, width=e.width))

        pairs: list[tuple[dict, tk.BooleanVar]] = []
        for group in manifest.PLAN_GROUPS:
            vols = plan.get(group) or []
            if not vols:
                continue
            ttk.Label(
                body, text=f"{self.PLAN_GROUP_LABELS[group]}　{len(vols)} 卷",
                font=FB,
            ).pack(anchor="w", pady=(10, 2))
            default = group in manifest.PLAN_DEFAULT_CHECKED
            for v in vols:
                var = tk.BooleanVar(value=default)
                pairs.append((v, var))
                label = format_index_token(
                    v.get("seq_index", v.get("index", 0)),
                    v.get("seq_total", total), "padded",
                    SIDE_INDEX_PREFIX if v.get("category") == "side" else "",
                )
                ttk.Checkbutton(
                    body, variable=var, text=f"  {label}  {v['name']}"
                ).pack(anchor="w", fill="x", padx=12, pady=1)

        def _download():
            picked = [v for v, var in pairs if var.get()]
            win.destroy()
            if not picked:
                self._set_status("沒有勾選任何卷", "info")
                return
            self._start_download(picked)

        btns = ttk.Frame(win)
        btns.pack(pady=(8, 12))
        ttk.Button(btns, text="下載選取", command=_download, width=10).pack(
            side="left", padx=4, ipady=4
        )
        ttk.Button(btns, text="關閉", command=win.destroy, width=10).pack(
            side="left", padx=4, ipady=4
        )

    def _open_preview_dialog(self, book_name: str, volumes: list[dict],
                             only_vid: int | None = None):
        """分類確認視窗。

        only_vid 不是 None 時（使用者貼的是單卷網址）只顯示、只帶出那一卷，
        但**編號仍照整份目錄算**：seq_index / seq_total 要靠全部卷才算得出來，
        只拿一卷去 resequence 會把它編成 1，檔名跟其他卷對不上。
        """
        win = tk.Toplevel(self.root)
        win.title(f"確認分類 - {book_name}")
        win.resizable(True, True)
        win.geometry("480x520")
        win.minsize(360, 300)
        win.grab_set()

        display = [v for v in volumes if only_vid is None or v["vid"] == only_vid]
        if not display:
            display = volumes
            only_vid = None

        header = f"書名：{book_name}　共 {len(volumes)} 卷"
        if only_vid is not None:
            header += f"（只載入 1 卷：{display[0]['name']}）"
        ttk.Label(win, text=header, font=FB).pack(
            anchor="w", padx=12, pady=(12, 6)
        )

        list_outer = ttk.Frame(win)
        list_outer.pack(fill="both", expand=True, padx=12)
        list_outer.columnconfigure(0, weight=1)
        list_outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(list_outer, highlightthickness=0)
        sb = ttk.Scrollbar(list_outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self._bind_wheel_to_dialog(win, canvas)

        row_frame = ttk.Frame(canvas)
        row_win = canvas.create_window((0, 0), window=row_frame, anchor="nw")
        row_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(row_win, width=e.width),
        )

        batch_vars: list[tk.BooleanVar] = []
        category_vars: list[tk.StringVar] = []

        for v in display:
            row = ttk.Frame(row_frame)
            row.pack(fill="x", padx=4, pady=2)
            bvar = tk.BooleanVar(value=False)
            batch_vars.append(bvar)
            ttk.Checkbutton(row, variable=bvar).pack(side="left")
            ttk.Label(row, text=v["name"], font=F, anchor="w").pack(
                side="left", padx=(4, 8), fill="x", expand=True
            )
            cvar = tk.StringVar(value="正式卷" if v["category"] == "main" else "外傳")
            category_vars.append(cvar)
            ttk.Combobox(
                row, textvariable=cvar, values=["正式卷", "外傳"],
                state="readonly", width=8, font=F
            ).pack(side="right")

        def _select_all_batch(state: bool):
            for bv in batch_vars:
                bv.set(state)

        def _mark_selected(label: str):
            for bv, cv in zip(batch_vars, category_vars):
                if bv.get():
                    cv.set(label)

        btn_row1 = ttk.Frame(win)
        btn_row1.pack(fill="x", padx=12, pady=(8, 0))
        ttk.Button(
            btn_row1, text="全選", command=lambda: _select_all_batch(True), width=8
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            btn_row1, text="全不選", command=lambda: _select_all_batch(False), width=8
        ).pack(side="left")
        ttk.Button(
            btn_row1, text="已選標為正式卷",
            command=lambda: _mark_selected("正式卷"), width=14
        ).pack(side="right", padx=(4, 0))
        ttk.Button(
            btn_row1, text="已選標為外傳",
            command=lambda: _mark_selected("外傳"), width=12
        ).pack(side="right")

        def _confirm():
            # 只有顯示出來的那幾卷有下拉選單；沒顯示的維持原本分類。
            edits = {
                v["vid"]: ("main" if cv.get() == "正式卷" else "side")
                for v, cv in zip(display, category_vars)
            }
            edited = [
                {**v, "category": edits.get(v["vid"], v["category"])}
                for v in volumes
            ]
            # 先用整份目錄算編號，再篩出要帶進下載清單的卷
            resequenced = resequence_by_category(edited)
            final_volumes = [
                v for v in resequenced
                if only_vid is None or v["vid"] == only_vid
            ]
            self._book_name = book_name
            self._volumes = final_volumes
            self._catalog_volumes = resequenced
            title = f"書名：{book_name}　共 {len(final_volumes)} 卷"
            if only_vid is not None:
                title += "（單卷）"
            self.title_label.config(text=title)
            self._build_checkbox_list(final_volumes)
            self.progress_label.config(text="載入完成，勾選要下載的卷後按「下載選取」")
            self.btn_download.config(state="normal")
            self.btn_select_all.config(state="normal")
            self.btn_deselect_all.config(state="normal")
            self.btn_scan.config(state="normal")
            self.btn_update.config(state="normal")
            self._set_status(
                f"已載入：{book_name}，共 {len(final_volumes)} 卷", "success"
            )
            win.destroy()
            # 載入完就地比對一次資料夾（純本地，目錄剛抓過不重抓），
            # 資料夾裡已經有檔案時直接告訴使用者，不用等他自己按「更新」
            self._notify_existing_files()

        def _cancel():
            self._aid = None
            self._book_name = None
            self._volumes = []
            self._reset_book_state()
            self.title_label.config(text="（輸入網址後點「載入」）")
            self.progress_label.config(text="等待中...")
            self._set_status("已取消載入", "info")
            win.destroy()

        btn_row2 = ttk.Frame(win)
        btn_row2.pack(pady=(8, 12))
        ttk.Button(btn_row2, text="確認", command=_confirm, width=10).pack(
            side="left", padx=4, ipady=4
        )
        ttk.Button(btn_row2, text="取消", command=_cancel, width=10).pack(
            side="left", padx=4, ipady=4
        )
        win.protocol("WM_DELETE_WINDOW", _cancel)

    def _select_all(self, state: bool):
        for var in self._check_vars:
            var.set(state)

    def _bind_wheel_to_dialog(self, win: tk.Toplevel, canvas: tk.Canvas):
        """對話框專用的滾輪綁定。

        **對話框不可以用 `_enable_wheel_scroll()`**——那個走 `root.bind_all`，
        是 App 層級的永久綁定，從來不解綁；每開一次對話框就多洩漏一個 handler，
        之後每次滾輪都要多跑一次已銷毀 canvas 的 `winfo_ismapped()`。

        綁在對話框自己的 Toplevel 上就沒這問題：子元件的 `<MouseWheel>` 會沿
        bindtags 冒泡到所屬 Toplevel，照樣收得到；`win.destroy()` 時綁定跟著消失。
        """
        win.bind(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )

    def _enable_wheel_scroll(self, canvas: tk.Canvas):
        """
        讓滑鼠停在 canvas 內任何子元件（Label、Checkbutton...）上方滾動滾輪也能捲動。
        Tkinter 的 <MouseWheel> 綁在 canvas 本身時，滑鼠移到子元件上方就收不到事件了
        （子元件會攔截），所以改用 bind_all 綁在整個 App 層級，用 winfo_ismapped()
        確保只有目前實際顯示的分頁會真的捲動，彼此不會互相干擾。
        """
        def handler(event):
            # canvas 可能屬於已關閉的對話框（如 Preview dialog），widget 銷毀後
            # winfo_ismapped() 會丟 TclError；此時視為「未顯示」，靜默略過即可。
            try:
                if canvas.winfo_ismapped():
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass
        self.root.bind_all("<MouseWheel>", handler, add="+")

    # ---- 載入目錄 ----

    def _on_load(self):
        url = self.url_var.get().strip()
        try:
            aid = parse_aid_from_url(url)
        except ValueError:
            self._set_status("網址格式錯誤，找不到 aid 參數", "error")
            return

        # 單卷網址：?vid=Y 直接就是 vid；章節頁 /novel/{分類}/{aid}/{cid}.htm
        # 只給得到 cid，要等目錄抓回來才反查得出屬於哪一卷。
        single_vid = parse_vid_from_url(url)
        single_cid = None if single_vid else parse_cid_from_url(url)

        self._aid = aid
        self._reset_book_state()
        self._single_vid = single_vid
        self._single_cid = single_cid
        self._source_url = url
        self.btn_load.config(state="disabled")
        self.title_label.config(text="載入中...")
        self.progress_bar.config(mode="indeterminate")
        self.progress_bar.start(10)
        # 單卷模式也一樣要整份抓目錄（編號要靠全部卷才算得出來），所以訊息講「模式」
        # 而不是「只抓一卷」——後者會讓使用者以為抓的東西變少了
        mode = "（單卷模式）" if (single_vid or single_cid) else ""
        self.progress_label.config(text=f"正在取得目錄{mode}...")
        self._set_status(f"正在載入書籍目錄{mode}...", "info")

        def _load_worker():
            try:
                soup = fetch_catalog(aid)
                book_name = parse_book_title(soup)
                volumes = parse_volumes(soup)
                self.msg_queue.put(("catalog_done", book_name, volumes))
            except Exception as e:
                # 只把類型 + status code 往下傳供落檔用，str(e) 只給畫面顯示，不落檔
                self.msg_queue.put(("catalog_error", str(e), type(e).__name__, _extract_status(e)))

        threading.Thread(target=_load_worker, daemon=True).start()

    # ---- 下載 ----

    def _on_download(self):
        if not self._volumes:
            return
        selected = [v for v, var in zip(self._volumes, self._check_vars) if var.get()]
        if not selected:
            self._set_status("請至少勾選一卷", "error")
            return
        self._start_download(selected)

    def _start_download(self, selected: list[dict]):
        """實際派工下載。_on_download（勾選清單）與更新視窗共用同一條路徑。"""
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            return
        # 書號與來源網址在這裡記一次。`_make_plan()` 也會記，但它只在輸出資料夾
        # **已經存在**時才跑得到（見 `_notify_existing_files()` 的前置檢查），
        # 所以第一次下載到全新資料夾的路徑會整個跳過它——實測 57 卷下載完
        # source_url 是空的就是這個洞。這裡是使用者確定要下載的時點，
        # `_ensure_output_dir()` 也已經把資料夾建好了，補記最安全。
        manifest.record_book_meta(output_dir, self._aid, self._book_name,
                                  self._source_url)
        self.btn_download.config(state="disabled")
        self.btn_update.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_scan.config(state="disabled")
        self._repair_mode = False
        self._auto_repair_active = False
        self._auto_round = 0
        self._last_batch_vids = {v["vid"] for v in selected}
        self._skip_event.clear()
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
        self.btn_skip.config(state="normal")
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")
        self.progress_bar.stop()
        self.progress_bar.config(mode="determinate")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(selected)
        self._set_status(f"下載中... 共 {len(selected)} 卷", "info")

        threading.Thread(
            target=run_download_all,
            args=(self._aid, self._book_name, selected, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay,
                  self._fname_index, self._fname_book_name, self._fname_separator),
            kwargs={"skip_event": self._skip_event,
                    "convert_traditional": self._convert_traditional,
                    "request_interval": self._request_interval},
            daemon=True,
        ).start()

    def _on_recover(self):
        if not self._recovery_volumes:
            return
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            return
        vols = list(self._recovery_volumes)
        self._recovery_volumes = []
        self._auto_repair_active = False
        self._dispatch_repair(vols, output_dir, f"重試/修復 {len(vols)} 卷")

    # 有限重試模式下，自動修復整批最多跑幾輪；無限重試模式一律只跑 1 輪
    AUTO_REPAIR_ROUND_LIMIT = 3
    # 無限重試模式下，自動修復流程中單一編碼嘗試的次數上限
    AUTO_REPAIR_MAX_ATTEMPTS = 50

    def _dispatch_repair(self, vols, output_dir, log_label, max_attempts=None):
        """共用的修復執行緒派工，_on_recover()（手動）與自動修復流程都呼叫這個。"""
        self._last_batch_vids = {v["vid"] for v in vols}
        self._repair_mode = True
        self._skip_event.clear()
        self.btn_recover.config(state="disabled", text="重試/修復")
        self.btn_manage.config(state="disabled")
        self.btn_download.config(state="disabled")
        self.btn_load.config(state="disabled")
        self.btn_select_all.config(state="disabled")
        self.btn_deselect_all.config(state="disabled")
        self.btn_scan.config(state="disabled")
        self.btn_update.config(state="disabled")
        self.btn_skip.config(state="normal")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"\n── {log_label} ──\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        self.progress_bar["value"] = 0
        self.progress_bar["maximum"] = len(vols)
        self._set_status(f"處理中... 共 {len(vols)} 卷", "info")
        kwargs = {"skip_event": self._skip_event,
                  "convert_traditional": self._convert_traditional,
                  "request_interval": self._request_interval}
        if max_attempts is not None:
            kwargs["max_attempts"] = max_attempts
        threading.Thread(
            target=run_repair_all,
            args=(self._aid, self._book_name, vols, output_dir, self.msg_queue,
                  self._retry_count, self._retry_delay,
                  self._fname_index, self._fname_book_name, self._fname_separator),
            kwargs=kwargs,
            daemon=True,
        ).start()

    def _start_auto_repair(self):
        """下載完成後若有失敗/亂碼卷，自動觸發修復（不用使用者按按鈕）。"""
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            self._auto_repair_active = False
            return
        vols = list(self._recovery_volumes)
        self._recovery_volumes = []
        self._auto_repair_active = True
        self._auto_round = 1
        infinite = self._retry_count <= 0
        max_attempts = self.AUTO_REPAIR_MAX_ATTEMPTS if infinite else None
        self._dispatch_repair(vols, output_dir, f"自動修復 第1輪 共 {len(vols)} 卷", max_attempts)

    def _on_scan(self):
        if not self._volumes:
            return
        output_dir = self._ensure_output_dir()
        if output_dir is None:
            return
        found = scan_existing_volumes(
            self._volumes, output_dir, self._book_name,
            self._fname_index, self._fname_book_name, self._fname_separator,
            convert_traditional=self._convert_traditional,
        )
        existing_vids = {v["vid"] for v in self._recovery_volumes}
        self._recovery_volumes += [v for v in found if v["vid"] not in existing_vids]
        n = len(self._recovery_volumes)
        if n:
            self.btn_recover.config(state="normal", text=f"重試/修復 {n} 卷")
            self.btn_manage.config(state="normal")
        if found:
            self._set_status(f"掃描完成，發現 {len(found)} 卷缺檔/亂碼", "info")
        else:
            self._set_status("掃描完成，沒有發現問題", "success")

    def _on_skip(self):
        self._skip_event.set()

    def _manage_recovery_dialog(self):
        if not self._recovery_volumes:
            return
        fail_list = list(self._recovery_volumes)
        win = tk.Toplevel(self.root)
        win.title("管理待處理卷")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text="取消勾選 = 移出重試列表", font=FH, foreground="gray").pack(
            anchor="w", padx=16, pady=(12, 4)
        )

        frame_outer = ttk.Frame(win)
        frame_outer.pack(fill="both", padx=12, pady=(0, 4))
        canvas_h = min(len(fail_list) * 28, 280)
        dlg_canvas = tk.Canvas(frame_outer, highlightthickness=0, height=canvas_h)
        dlg_sb = ttk.Scrollbar(frame_outer, orient="vertical", command=dlg_canvas.yview)
        dlg_canvas.configure(yscrollcommand=dlg_sb.set)
        dlg_canvas.pack(side="left", fill="both", expand=True)
        dlg_sb.pack(side="right", fill="y")
        cb_frame = ttk.Frame(dlg_canvas)
        cb_win = dlg_canvas.create_window((0, 0), window=cb_frame, anchor="nw")
        cb_frame.bind(
            "<Configure>",
            lambda e: dlg_canvas.configure(scrollregion=dlg_canvas.bbox("all")),
        )
        dlg_canvas.bind(
            "<Configure>",
            lambda e: dlg_canvas.itemconfig(cb_win, width=e.width),
        )
        dlg_canvas.bind(
            "<MouseWheel>",
            lambda e: dlg_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"),
        )

        check_vars = []
        for vol in fail_list:
            var = tk.BooleanVar(value=True)
            check_vars.append(var)
            ttk.Checkbutton(cb_frame, text=vol["name"], variable=var).pack(
                anchor="w", padx=8, pady=2
            )

        def _apply():
            kept = [v for v, var in zip(fail_list, check_vars) if var.get()]
            self._recovery_volumes = kept
            n = len(kept)
            if n:
                self.btn_recover.config(state="normal", text=f"重試/修復 {n} 卷")
                self.btn_manage.config(state="normal")
            else:
                self.btn_recover.config(state="disabled", text="重試/修復")
                self.btn_manage.config(state="disabled")
            win.destroy()

        btn_row = ttk.Frame(win)
        btn_row.pack(pady=(12, 16))
        ttk.Button(btn_row, text="確認", command=_apply, width=10).pack(
            side="left", padx=4, ipady=4
        )
        ttk.Button(btn_row, text="取消", command=win.destroy, width=10).pack(
            side="left", padx=4, ipady=4
        )

    # ---- Queue 輪詢 ----

    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]

                if kind == "catalog_done":
                    _, book_name, volumes = msg
                    self.progress_bar.stop()
                    self.progress_bar.config(mode="determinate")
                    self.btn_load.config(state="normal")
                    classified = assign_categories_and_sequence(volumes, self._side_keywords)
                    only_vid = self._single_vid
                    if only_vid is None and self._single_cid is not None:
                        hit = find_volume_by_cid(classified, self._single_cid)
                        only_vid = hit["vid"] if hit else None
                    if (only_vid is not None
                            and not any(v["vid"] == only_vid for v in classified)):
                        only_vid = None
                        self._set_status(
                            "網址指定的卷不在目錄中，改為載入整套", "info"
                        )
                    self._single_vid = only_vid
                    self._open_preview_dialog(book_name, classified, only_vid)

                elif kind == "update_catalog":
                    _, book_name, volumes = msg
                    self.progress_bar.stop()
                    self.progress_bar.config(mode="determinate")
                    self.btn_load.config(state="normal")
                    self.btn_update.config(state="normal")
                    self._updating = False
                    self._book_name = book_name
                    self._catalog_volumes = volumes
                    # 更新一律針對整套目錄比對：單卷模式下 _volumes 只有一卷，
                    # 拿它比對會看不到其他卷的新舊狀態。
                    self._volumes = volumes
                    self._build_checkbox_list(volumes)
                    self.title_label.config(
                        text=f"書名：{book_name}　共 {len(volumes)} 卷"
                    )
                    self.btn_download.config(state="normal")
                    self.btn_select_all.config(state="normal")
                    self.btn_deselect_all.config(state="normal")
                    self.btn_scan.config(state="normal")
                    output_dir = self._path_var.get().strip()
                    try:
                        plan = self._make_plan(volumes, output_dir)
                    except OSError as e:
                        _write_log(log_t("err.manifest", aid=self._aid,
                                         op="plan", etype=type(e).__name__),
                                   "ERROR")
                        self._set_status("比對失敗，無法讀取輸出資料夾", "error")
                        continue
                    need = plan["new"] + plan["incomplete"]
                    self._apply_plan_selection({v["vid"] for v in need})
                    if not any(plan[g] for g in manifest.PLAN_GROUPS
                               if g != "ok"):
                        self._set_status("已是最新，沒有需要下載的卷", "success")
                    else:
                        self._set_status(
                            f"共 {len(volumes)} 卷，需要下載 {len(need)} 卷", "info"
                        )
                        self._open_update_dialog(plan, len(volumes))

                elif kind == "catalog_error":
                    _, err, err_type, status = msg
                    self.progress_bar.stop()
                    self.progress_bar.config(mode="determinate")
                    self.title_label.config(text="載入失敗")
                    self.progress_label.config(text="載入失敗，請確認網址")
                    self.btn_load.config(state="normal")
                    # 更新流程也走這條錯誤路徑，卡住的旗標與按鈕要一起解開，
                    # 否則抓目錄失敗一次之後「更新」就再也按不下去
                    if self._updating:
                        self._updating = False
                        self.btn_update.config(state="normal")
                    else:
                        self.btn_select_all.config(state="disabled")
                        self.btn_deselect_all.config(state="disabled")
                    hint = "（403 錯誤：網站拒絕存取，可稍後再試）" if status == 403 else ""
                    self._set_status(f"載入失敗：{err}{hint}", "error")
                    # 只記類型 + status code + 書號，絕不記 url / response 全文
                    _write_log(log_t("err.catalog", aid=self._aid,
                                     etype=err_type, status=status), "ERROR")

                elif kind == "progress":
                    _, current, total, vol_name = msg
                    self.progress_bar["value"] = current
                    self.progress_bar["maximum"] = total
                    self.progress_label.config(
                        text=f"正在下載 {current:02d}/{total}：{vol_name}"
                    )

                elif kind == "log":
                    _, status, index_str, vol_name, detail = msg
                    icon = {"ok": "✅", "warn": "⚠️", "skip": "⏭️"}.get(status, "❌")
                    line = f"{icon} {index_str} {vol_name}"
                    if detail:
                        line += f"（{detail}）"
                    self.log_text.config(state="normal")
                    self.log_text.insert("end", line + "\n")
                    self.log_text.see("end")
                    self.log_text.config(state="disabled")

                elif kind == "done":
                    _, success_count, fail_volumes, garbled_volumes = msg
                    batch_fail_count = len(fail_volumes)
                    batch_garbled_count = len(garbled_volumes)
                    if self._repair_mode:
                        total = success_count + batch_fail_count + batch_garbled_count
                    else:
                        total = success_count + batch_fail_count
                    # 合併而非覆蓋：保留其他批次尚未解決的卷，只更新本批次涵蓋到的卷
                    attempted = self._last_batch_vids
                    self._recovery_volumes = [
                        v for v in self._recovery_volumes if v["vid"] not in attempted
                    ] + fail_volumes + garbled_volumes
                    recovery_count = len(self._recovery_volumes)
                    self.btn_load.config(state="normal")
                    self.btn_download.config(state="normal")
                    self.btn_select_all.config(state="normal")
                    self.btn_deselect_all.config(state="normal")
                    self.btn_scan.config(state="normal")
                    self.btn_update.config(state="normal")
                    self.btn_skip.config(state="disabled")
                    if recovery_count:
                        self.btn_recover.config(
                            state="normal", text=f"重試/修復 {recovery_count} 卷"
                        )
                        self.btn_manage.config(state="normal")
                    else:
                        self.btn_recover.config(state="disabled", text="重試/修復")
                        self.btn_manage.config(state="disabled")
                    self.progress_bar["value"] = total
                    self.progress_label.config(text=f"完成 {success_count}/{total} 卷")
                    if fail_volumes or garbled_volumes:
                        level = "error" if fail_volumes else "info"
                        parts = []
                        if fail_volumes:
                            parts.append(f"失敗：{', '.join(v['name'] for v in fail_volumes)}")
                        if garbled_volumes:
                            parts.append(f"亂碼：{', '.join(v['name'] for v in garbled_volumes)}")
                        suffix = "，" + "；".join(parts)
                    else:
                        level = "success"
                        suffix = ""
                    prefix = "修復完成" if self._repair_mode else "下載完成"
                    self._set_status(f"{prefix} {success_count}/{total}{suffix}", level)

                    if self._auto_repair_active:
                        infinite = self._retry_count <= 0
                        round_limit = 1 if infinite else self.AUTO_REPAIR_ROUND_LIMIT
                        if recovery_count == 0:
                            self._auto_repair_active = False
                        elif self._auto_round >= round_limit:
                            self._auto_repair_active = False
                            self._set_status(
                                f"自動處理完成，成功 {success_count}/{total} 卷，"
                                f"{recovery_count} 卷需要你手動處理"
                                "（可點「重試/修復」再試）",
                                "error",
                            )
                        else:
                            self._auto_round += 1
                            auto_output_dir = self._ensure_output_dir()
                            if auto_output_dir is None:
                                self._auto_repair_active = False
                            else:
                                next_vols = list(self._recovery_volumes)
                                self._recovery_volumes = []
                                max_attempts = self.AUTO_REPAIR_MAX_ATTEMPTS if infinite else None
                                self._dispatch_repair(
                                    next_vols, auto_output_dir,
                                    f"自動修復 第{self._auto_round}輪 共 {len(next_vols)} 卷",
                                    max_attempts,
                                )
                    elif not self._repair_mode and recovery_count > 0:
                        self._start_auto_repair()

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


def _pick_language_on_first_run(root: tk.Tk) -> None:
    """首次啟動時問一次語言，選完寫進 .tool_config.json，之後不再出現。

    視窗刻意**不翻譯**：這時候還不知道使用者要哪個語言，用任一種當說明都
    在賭。只有一個英文抬頭，其餘全是各語言的自稱，看得懂哪個就點哪個。

    直接關掉視窗＝接受第一個選項並**照樣存檔**——需求是「選完就記住不要再
    跳」，關掉還一直跳才是煩人。選錯了在「設定」分頁隨時能改。
    """
    cfg = load_config()
    if i18n.is_supported(cfg.get("language", "")):
        return                      # 選過了，直接進主畫面

    choices = i18n.available_languages()
    chosen = {"code": choices[0][0]}

    dlg = tk.Toplevel(root)
    dlg.title("Language")
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)

    ttk.Label(dlg, text="Select your language",
              font=("", 12, "bold")).pack(padx=28, pady=(20, 4))
    ttk.Label(dlg, text="You can change this later in Settings.",
              foreground="#555555").pack(padx=28, pady=(0, 14))

    def _choose(code: str) -> None:
        chosen["code"] = code
        dlg.destroy()

    for code, name in choices:
        ttk.Button(dlg, text=name, width=20,
                   command=lambda c=code: _choose(c)).pack(padx=28, pady=3)
    ttk.Frame(dlg, height=10).pack()

    dlg.update_idletasks()
    x = root.winfo_rootx() + (root.winfo_width() - dlg.winfo_width()) // 2
    y = root.winfo_rooty() + (root.winfo_height() - dlg.winfo_height()) // 3
    dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    dlg.grab_set()
    dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)   # 關掉＝用預設值，照樣存
    root.wait_window(dlg)

    save_config({"language": chosen["code"]})


def main():
    show_cth_banner()
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.update()
    root.attributes("-topmost", False)
    _pick_language_on_first_run(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
