import html
import os
import time
import queue
from curl_cffi import requests as cf_requests
from src import manifest
from src.config import DOWNLOAD_BASE_URL, RETRY_COUNT, RETRY_DELAY
from src.converter import convert_to_traditional
from src.verify import verify_file
from src.scraper import format_index_token
from src.logutil import _write_log, _write_log_header, _extract_status
from src.logtext import log_t
from src.sitedata import SIDE_INDEX_PREFIX
from src.i18n import t

_session: cf_requests.Session | None = None


def _get_session() -> cf_requests.Session:
    global _session
    if _session is None:
        _session = cf_requests.Session()
    return _session


def _fetch_bytes(aid: str, vid: int, charset: str,
                 retry_count: int, retry_delay: float,
                 skip_event=None, max_attempts: int | None = None) -> bytes | None:
    """retry_count <= 0 表示無限重試，直到成功或 skip_event 被觸發。
    max_attempts 有設定時，即使無限重試模式也會在達到次數上限後放棄
    （自動修復流程用來避免真的下載不到的卷讓程式無限空轉；手動操作不傳這個參數）。"""
    url = f"{DOWNLOAD_BASE_URL}?aid={aid}&vid={vid}&charset={charset}"
    infinite = retry_count <= 0
    attempt = 0
    while True:
        attempt += 1
        if skip_event and skip_event.is_set():
            return None
        resp = None
        try:
            resp = _get_session().get(url, impersonate="chrome120", timeout=30)
            resp.raise_for_status()
            # 回應內容不應是 HTML（< 開頭 = 錯誤頁面）
            if len(resp.content) < 50 or resp.content[:5].strip().startswith(b"<"):
                raise ValueError("Response is HTML error page, not TXT")
            return resp.content
        except Exception as e:
            # 只記類型 + status code + 重試次數，絕不記 url（見 windows-tool.md「錯誤行怎麼寫」）
            status = resp.status_code if resp is not None else _extract_status(e)
            retry_label = (log_t("retry.infinite") if infinite
                           else f"{attempt}/{retry_count}")
            _write_log(log_t("err.fetch", vid=vid, charset=charset,
                             etype=type(e).__name__, status=status,
                             retry=retry_label), "ERROR")
            if not infinite and attempt >= retry_count:
                return None
            if max_attempts is not None and attempt >= max_attempts:
                return None
            if skip_event and skip_event.is_set():
                return None
            time.sleep(retry_delay)


def _decode_response(raw: bytes, charset_hint: str) -> str:
    """
    wenku8 的 charset query 參數不可信：實測 charset=utf-8 實際回傳的是
    UTF-16 LE bytes（帶 BOM），charset=big5 實際回傳的是 UTF-8（帶 BOM）。
    一律先偵測 BOM，偵測不到才照參數名稱猜測解碼。
    來源 txt 內文常殘留未轉譯的 HTML 實體（如 &#8231; 間隔號），一併 unescape。
    """
    if raw.startswith(b"\xff\xfe"):
        text = raw[2:].decode("utf-16-le", errors="replace")
    elif raw.startswith(b"\xfe\xff"):
        text = raw[2:].decode("utf-16-be", errors="replace")
    elif raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig", errors="replace")
    else:
        text = raw.decode(charset_hint, errors="replace")
    return html.unescape(text)


def _fetch_best_text(aid: str, vid: int,
                     retry_count: int, retry_delay: float,
                     skip_event=None, max_attempts: int | None = None) -> str | None:
    """先抓 UTF-8，若含亂碼字元就自動改抓 GBK 版本並取亂碼較少者。"""
    utf8_bytes = _fetch_bytes(aid, vid, "utf-8", retry_count, retry_delay, skip_event, max_attempts)
    if utf8_bytes is None:
        return None
    utf8_text = _decode_response(utf8_bytes, "utf-8")

    if "�" not in utf8_text or (skip_event and skip_event.is_set()):
        return utf8_text

    gbk_bytes = _fetch_bytes(aid, vid, "gbk", retry_count, retry_delay, skip_event, max_attempts)
    if gbk_bytes is not None:
        gbk_text = _decode_response(gbk_bytes, "gbk")
        if gbk_text.count("�") < utf8_text.count("�"):
            return gbk_text
    return utf8_text


def download_volume(aid: str, vid: int, filepath: str,
                    retry_count: int = RETRY_COUNT,
                    retry_delay: float = RETRY_DELAY,
                    skip_event=None, convert_traditional: bool = True) -> bool:
    if skip_event and skip_event.is_set():
        return False
    text = _fetch_best_text(aid, vid, retry_count, retry_delay, skip_event)
    if text is None:
        return False
    converted = convert_to_traditional(text) if convert_traditional else text
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(converted)
    return True


def check_garbled(filepath: str) -> bool:
    try:
        with open(filepath, encoding="utf-8") as f:
            return "�" in f.read()
    except (UnicodeDecodeError, OSError):
        return True


REPAIR_STALE_LIMIT = 5  # 連續幾輪沒有改善才放棄（避免真的修不好時無限卡住）


def repair_volume(aid: str, vid: int, filepath: str,
                  retry_count: int = RETRY_COUNT,
                  retry_delay: float = RETRY_DELAY,
                  skip_event=None, max_attempts: int | None = None,
                  convert_traditional: bool = True) -> bool | None:
    """
    重複整輪重新下載（utf-8 + gbk 挑亂碼較少者），直到完全無亂碼、或
    skip_event 被觸發才停止。retry_count 為正數（有限重試）時，額外會在
    連續 REPAIR_STALE_LIMIT 輪都沒有改善時提早放棄；retry_count <= 0
    （無限重試）時則完全依照使用者設定，只靠 skip_event 才會停止。

    Returns False = 修復成功（無亂碼）
            True  = 仍有亂碼（放棄前已盡量取最佳結果）
            None  = 從未成功取得任何內容（網路失敗或一開始就被跳過）
    """
    infinite = retry_count <= 0
    best_text: str | None = None
    best_count: int | None = None
    stale_rounds = 0

    while True:
        if skip_event and skip_event.is_set():
            break
        text = _fetch_best_text(aid, vid, retry_count, retry_delay, skip_event, max_attempts)
        if text is not None:
            count = text.count("�")
            if best_count is None or count < best_count:
                best_text, best_count = text, count
                stale_rounds = 0
            else:
                stale_rounds += 1
            if count == 0:
                break
        else:
            stale_rounds += 1

        if skip_event and skip_event.is_set():
            break
        if (not infinite or max_attempts is not None) and stale_rounds >= REPAIR_STALE_LIMIT:
            break
        time.sleep(retry_delay)

    if best_text is None:
        return None

    converted = convert_to_traditional(best_text) if convert_traditional else best_text
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(converted)

    return True if "�" in converted else False


def build_filepath(output_dir: str, book_name: str, volume_index: int,
                   volume_name: str, total: int,
                   index_fmt: str = "padded",
                   include_book_name: bool = True,
                   separator: str = " ",
                   index_prefix: str = "",
                   convert_traditional: bool = False) -> str:
    """組出單卷的完整輸出路徑。

    convert_traditional 跟內文轉換共用同一個設定：勾了簡轉繁，檔名裡的書名與
    卷名（都是從簡體站抓回來的原文）也一起轉。轉換要在 safe() 濾掉非法字元
    **之前**做——OpenCC 是詞庫式轉換，先把字元挖掉會影響上下文判斷。

    ⚠ 這個函式是檔名的唯一真相來源，下載、修復、掃描、manifest 比對四條路徑
    全都走它。convert_traditional 少傳給其中任何一條，就會變成「寫檔用繁體
    檔名、找檔用簡體檔名」，結果是每一卷都被判定缺檔然後整套重抓。

    預設 False 是刻意的：漏傳時維持既有行為（不轉），不會靜默改掉檔名。
    """
    safe = lambda s: "".join(c for c in s if c not in r'\/:*?"<>|')
    if convert_traditional:
        book_name = convert_to_traditional(book_name)
        volume_name = convert_to_traditional(volume_name)
    parts = []
    token = format_index_token(volume_index, total, index_fmt, index_prefix)
    if token:
        parts.append(safe(token))
    if include_book_name:
        parts.append(safe(book_name))
    parts.append(safe(volume_name))
    safe_sep = safe(separator) or " "
    filename = safe_sep.join(parts) + ".txt"
    return os.path.join(output_dir, filename)


# 哪些「可疑」的判定結果值得自動重抓一次。
#
# 只有錨點類的理由進來：那是**有證據**的判定——目錄說有這幾章，檔案裡找不到，
# 幾乎一定是伺服器回了截斷的內容。"too_short" 刻意不列入：它是沒有任何章節錨點
# 時才會走到的字數 fallback，而插圖卷、後記這種卷本來就可能真的很短，自動重抓
# 只會讓它每次都被抓一遍又每次都判定可疑。那種情況仍會記進 manifest 標成
# suspect，在「更新」視窗的「不完整」那組列出來，由使用者自己決定要不要抓。
_AUTO_REPAIR_REASONS = ("anchor_ratio", "anchor_tail")


def _record_manifest(output_dir: str, aid: str, book_name: str, vol: dict,
                     filepath: str, convert_traditional: bool,
                     median: int | None) -> dict | None:
    """跑完整性判定並寫進 manifest，回傳判定結果（失敗回 None）。

    刻意讀回剛寫好的檔案而不是驗記憶體裡的字串：manifest 的 size 一定要取磁碟
    實測值（Windows text mode 會把 \\n 翻成 \\r\\n，bytes 跟記憶體算的對不上），
    順手用同一份磁碟內容做判定，兩邊來源一致。單卷 300KB 讀+掃約 5–10ms。

    任何失敗一律吞掉——紀錄掛掉不能拖垮下載。
    """
    try:
        script = manifest.script_for(convert_traditional)
        verdict = verify_file(filepath, vol.get("chapters"), median, script)
        if verdict is None:
            return None
        manifest.record_volume(output_dir, aid, book_name, vol, filepath,
                               verdict, script)
        return verdict
    except OSError:
        return None


def scan_existing_volumes(volumes: list[dict], output_dir: str, book_name: str,
                          index_fmt: str = "padded",
                          include_book_name: bool = True,
                          separator: str = " ",
                          convert_traditional: bool = False) -> list[dict]:
    """比對卷列表與資料夾實際檔案，回傳缺檔或含亂碼的卷清單。純檢查，不發網路請求。"""
    total = len(volumes)
    missing_or_garbled = []
    for vol in volumes:
        seq_index = vol.get("seq_index", vol["index"])
        seq_total = vol.get("seq_total", total)
        prefix = SIDE_INDEX_PREFIX if vol.get("category") == "side" else ""
        filepath = build_filepath(output_dir, book_name, seq_index, vol["name"], seq_total,
                                  index_fmt, include_book_name, separator,
                                  index_prefix=prefix,
                                  convert_traditional=convert_traditional)
        if not os.path.isfile(filepath) or check_garbled(filepath):
            missing_or_garbled.append(vol)
    return missing_or_garbled


def run_download_all(aid: str, book_name: str, volumes: list[dict],
                     output_dir: str, msg_queue: queue.Queue,
                     retry_count: int = RETRY_COUNT,
                     retry_delay: float = RETRY_DELAY,
                     index_fmt: str = "padded",
                     include_book_name: bool = True,
                     separator: str = " ",
                     skip_event=None, convert_traditional: bool = True) -> None:
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    garbled_volumes: list[dict] = []

    retry_label_hdr = (log_t("retry.infinite") if retry_count <= 0
                       else f"{retry_count}x")
    task_start = time.time()
    _write_log_header(log_t("hdr.download", book=book_name, total=total,
                            retry=retry_label_hdr))

    # 沒有章節錨點的卷（單章卷、全短標題卷）要靠同書已完成卷的字數中位數當基準，
    # 整批算一次就好，不必每卷重讀 manifest
    median = manifest.median_chars(manifest.load(output_dir), aid)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        seq_index = vol.get("seq_index", vol["index"])
        seq_total = vol.get("seq_total", total)
        prefix = SIDE_INDEX_PREFIX if vol.get("category") == "side" else ""
        index_str = format_index_token(seq_index, seq_total, "padded", prefix)
        try:
            filepath = build_filepath(output_dir, book_name, seq_index, vol["name"], seq_total,
                                      index_fmt, include_book_name, separator,
                                      index_prefix=prefix,
                                      convert_traditional=convert_traditional)
            ok = download_volume(aid, vol["vid"], filepath, retry_count, retry_delay,
                                 skip_event, convert_traditional)
            if ok:
                if skip_event and skip_event.is_set():
                    skip_event.clear()
                success += 1
                verdict = _record_manifest(output_dir, aid, book_name, vol,
                                           filepath, convert_traditional, median)
                if check_garbled(filepath):
                    garbled_volumes.append(vol)
                    msg_queue.put(("log", "warn", index_str, vol["name"],
                                   t("dl.detail.garbled")))
                elif verdict and verdict["reason"] in _AUTO_REPAIR_REASONS:
                    # 章節錨點對不上＝有證據顯示伺服器回了不完整的內容
                    # （HTTP 200 但內容被截斷）。併進 garbled_volumes 讓既有的
                    # 自動修復鏈重抓一次，不另外開一條流程。
                    garbled_volumes.append(vol)
                    msg_queue.put(("log", "warn", index_str, vol["name"],
                                   t("dl.detail.incomplete")))
                else:
                    msg_queue.put(("log", "ok", index_str, vol["name"], ""))
            else:
                skipped = skip_event is not None and skip_event.is_set()
                fail_volumes.append(vol)
                if skipped:
                    skip_event.clear()
                    msg_queue.put(("log", "skip", index_str, vol["name"],
                                   t("dl.detail.skipped")))
                else:
                    retry_label = (t("dl.retry.infinite") if retry_count <= 0
                                   else f"{retry_count}x")
                    msg_queue.put(("log", "fail", index_str, vol["name"],
                                   t("dl.detail.retry_failed", retry=retry_label)))
        except Exception as e:
            # 單一卷發生非預期錯誤（例如路徑無法寫入）不應讓整批下載卡死
            fail_volumes.append(vol)
            # 只記類型 + status code，絕不記 {e} 全文 / url；書名/卷序已在任務起始行
            status = _extract_status(e)
            _write_log(log_t("err.volume", book=book_name, index=index_str,
                             etype=type(e).__name__, status=status), "ERROR")
            msg_queue.put(("log", "fail", index_str, vol["name"],
                           t("dl.detail.error", err=e)))

    elapsed = int(time.time() - task_start)
    ok_all = not fail_volumes
    result_text = (
        log_t("result.ok", success=success, total=total) if ok_all
        else log_t("result.partial", success=success, total=total,
                   failed=len(fail_volumes))
    )
    _write_log(log_t("result.elapsed", result=result_text,
                     minutes=elapsed // 60, seconds=elapsed % 60),
               "OK" if ok_all else "FAIL")

    msg_queue.put(("done", success, fail_volumes, garbled_volumes))


def run_repair_all(aid: str, book_name: str, volumes: list[dict],
                   output_dir: str, msg_queue: queue.Queue,
                   retry_count: int = RETRY_COUNT,
                   retry_delay: float = RETRY_DELAY,
                   index_fmt: str = "padded",
                   include_book_name: bool = True,
                   separator: str = " ",
                   skip_event=None, max_attempts: int | None = None,
                   convert_traditional: bool = True) -> None:
    total = len(volumes)
    success = 0
    fail_volumes: list[dict] = []
    garbled_volumes: list[dict] = []

    retry_label_hdr = (log_t("retry.infinite") if retry_count <= 0
                       else f"{retry_count}x")
    task_start = time.time()
    _write_log_header(log_t("hdr.repair", book=book_name, total=total,
                            retry=retry_label_hdr))

    median = manifest.median_chars(manifest.load(output_dir), aid)

    for i, vol in enumerate(volumes, 1):
        msg_queue.put(("progress", i, total, vol["name"]))
        seq_index = vol.get("seq_index", vol["index"])
        seq_total = vol.get("seq_total", total)
        prefix = SIDE_INDEX_PREFIX if vol.get("category") == "side" else ""
        index_str = format_index_token(seq_index, seq_total, "padded", prefix)
        try:
            filepath = build_filepath(output_dir, book_name, seq_index, vol["name"], seq_total,
                                      index_fmt, include_book_name, separator,
                                      index_prefix=prefix,
                                      convert_traditional=convert_traditional)
            result = repair_volume(aid, vol["vid"], filepath, retry_count, retry_delay,
                                   skip_event, max_attempts, convert_traditional)
            skipped = skip_event is not None and skip_event.is_set()
            if skipped:
                skip_event.clear()
                garbled_volumes.append(vol)
                msg_queue.put(("log", "skip", index_str, vol["name"],
                               t("dl.detail.skipped")))
            elif result is None:
                fail_volumes.append(vol)
                msg_queue.put(("log", "fail", index_str, vol["name"],
                               t("dl.detail.repair_failed")))
            elif result is True:
                garbled_volumes.append(vol)
                msg_queue.put(("log", "warn", index_str, vol["name"],
                               t("dl.detail.still_garbled")))
            else:
                verdict = _record_manifest(output_dir, aid, book_name, vol,
                                           filepath, convert_traditional, median)
                if verdict and verdict["reason"] in _AUTO_REPAIR_REASONS:
                    garbled_volumes.append(vol)
                    msg_queue.put(("log", "warn", index_str, vol["name"],
                                   t("dl.detail.incomplete")))
                else:
                    success += 1
                    msg_queue.put(("log", "ok", index_str, vol["name"],
                                   t("dl.detail.repaired")))
        except Exception as e:
            # 單一卷發生非預期錯誤（例如路徑無法寫入）不應讓整批修復卡死
            fail_volumes.append(vol)
            # 只記類型 + status code，絕不記 {e} 全文 / url；書名/卷序已在任務起始行
            status = _extract_status(e)
            _write_log(log_t("err.volume", book=book_name, index=index_str,
                             etype=type(e).__name__, status=status), "ERROR")
            msg_queue.put(("log", "fail", index_str, vol["name"],
                           t("dl.detail.error", err=e)))

    elapsed = int(time.time() - task_start)
    ok_all = not fail_volumes
    result_text = (
        log_t("result.ok", success=success, total=total) if ok_all
        else log_t("result.partial", success=success, total=total,
                   failed=len(fail_volumes))
    )
    _write_log(log_t("result.elapsed", result=result_text,
                     minutes=elapsed // 60, seconds=elapsed % 60),
               "OK" if ok_all else "FAIL")

    msg_queue.put(("done", success, fail_volumes, garbled_volumes))
