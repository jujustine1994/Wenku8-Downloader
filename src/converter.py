import os
import queue

from opencc import OpenCC

_cc = OpenCC("s2twp")

_FALLBACK_ENCODINGS = (("utf-8", "utf-8"), ("gbk", "GBK"), ("big5", "Big5"))


def convert_to_traditional(text: str) -> str:
    return _cc.convert(text)


def _detect_and_decode(raw: bytes) -> tuple[str, str]:
    """
    智慧編碼偵測：先看 BOM，沒有 BOM 就依序嘗試 UTF-8/GBK/Big5，
    優先採用能完全乾淨解碼的編碼；都不乾淨則挑亂碼字元最少的。
    回傳 (解碼後文字, 編碼標籤)，標籤為 "utf-8" 代表沒有異常需要修正。
    """
    if raw.startswith(b"\xff\xfe"):
        return raw[2:].decode("utf-16-le", errors="replace"), "UTF-16 LE (BOM)"
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace"), "UTF-16 BE (BOM)"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace"), "UTF-8 (BOM)"

    for enc, label in _FALLBACK_ENCODINGS:
        try:
            return raw.decode(enc), label
        except UnicodeDecodeError:
            continue

    best_text, best_label, best_count = "", "utf-8", None
    for enc, label in _FALLBACK_ENCODINGS:
        text = raw.decode(enc, errors="replace")
        count = text.count("�")
        if best_count is None or count < best_count:
            best_text, best_label, best_count = text, label, count
    return best_text, best_label


def run_convert_all(
    files: list[str], output_mode: str, msg_queue: queue.Queue
) -> None:
    success = 0
    fail = 0
    for filepath in files:
        try:
            with open(filepath, "rb") as f:
                raw = f.read()
            text, enc_label = _detect_and_decode(raw)
            converted = convert_to_traditional(text)
            if output_mode == "overwrite":
                out_path = filepath
            else:
                base, ext = os.path.splitext(filepath)
                out_path = base + "_TC" + ext
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(converted)
            success += 1
            detail = "" if enc_label == "utf-8" else f"偵測為 {enc_label} 編碼，已修正"
            msg_queue.put(("conv_log", True, os.path.basename(filepath), detail))
        except Exception as e:
            fail += 1
            msg_queue.put(("conv_log", False, os.path.basename(filepath), str(e)))
    msg_queue.put(("conv_done", success, fail))
