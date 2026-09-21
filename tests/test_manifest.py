"""manifest.py 的單元測試。純本地檔案操作，不發網路請求。"""

import json
import os

from src import manifest


def _vol(vid, index=1, name="第一卷", cids=(1, 2, 3), category="main"):
    return {
        "vid": vid,
        "index": index,
        "seq_index": index,
        "seq_total": 3,
        "name": name,
        "category": category,
        "chapters": [{"cid": c, "title": f"第{c}章 『測試標題』"} for c in cids],
    }


def _build_path_fn(output_dir):
    return lambda vol: os.path.join(output_dir, f"{vol['seq_index']:02d} {vol['name']}.txt")


def _write(path, chars=9000):
    with open(path, "w", encoding="utf-8") as f:
        f.write("內" * chars)


COMPLETE = {"status": "complete", "chars": 9000, "anchor_hits": 3,
            "anchor_total": 3, "reason": ""}


# ── 讀寫 ──

def test_load_missing_returns_empty_skeleton(tmp_path):
    data = manifest.load(str(tmp_path))
    assert data == {"version": manifest.SCHEMA_VERSION, "books": {}}


def test_roundtrip_keeps_chinese_readable(tmp_path):
    out = str(tmp_path)
    vol = _vol(100, name="第一卷")
    path = os.path.join(out, "01 第一卷.txt")
    _write(path)
    manifest.record_volume(out, "1861", "測試書名", vol, path, COMPLETE,
                           manifest.SCRIPT_TRADITIONAL)

    raw = open(manifest.path_for(out), encoding="utf-8").read()
    assert "測試書名" in raw          # ensure_ascii=False 生效，沒被轉成 \uXXXX
    assert not raw.startswith("﻿")  # 不可有 BOM

    book = manifest.get_book(manifest.load(out), "1861")
    assert book["book_name"] == "測試書名"
    assert book["volumes"]["100"]["status"] == "complete"
    assert book["volumes"]["100"]["cids"] == [1, 2, 3]


def test_size_comes_from_disk_not_memory(tmp_path):
    """Windows text mode 會把 \\n 翻成 \\r\\n，size 必須取磁碟實測值。"""
    out = str(tmp_path)
    vol = _vol(100)
    path = os.path.join(out, "01 第一卷.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("一\n二\n三\n")
    manifest.record_volume(out, "1861", "書", vol, path, COMPLETE,
                           manifest.SCRIPT_TRADITIONAL)
    rec = manifest.get_book(manifest.load(out), "1861")["volumes"]["100"]
    assert rec["size"] == os.path.getsize(path)


def test_load_tolerates_bom(tmp_path):
    out = str(tmp_path)
    payload = json.dumps({"version": manifest.SCHEMA_VERSION,
                          "books": {"1": {"volumes": {}}}}, ensure_ascii=False)
    with open(manifest.path_for(out), "w", encoding="utf-8-sig") as f:
        f.write(payload)
    assert "1" in manifest.load(out)["books"]


def test_load_broken_json_returns_skeleton(tmp_path):
    out = str(tmp_path)
    with open(manifest.path_for(out), "w", encoding="utf-8") as f:
        f.write("{ this is not json")
    assert manifest.load(out)["books"] == {}


def test_load_unknown_version_returns_skeleton(tmp_path):
    out = str(tmp_path)
    with open(manifest.path_for(out), "w", encoding="utf-8") as f:
        json.dump({"version": 99, "books": {"1": {}}}, f)
    assert manifest.load(out)["books"] == {}


def test_two_books_in_one_folder_do_not_collide(tmp_path):
    out = str(tmp_path)
    for aid, vid, name in (("1861", 100, "甲卷"), ("1862", 200, "乙卷")):
        path = os.path.join(out, f"01 {name}.txt")
        _write(path)
        manifest.record_volume(out, aid, f"書{aid}", _vol(vid, name=name), path,
                               COMPLETE, manifest.SCRIPT_TRADITIONAL)
    data = manifest.load(out)
    assert set(data["books"]) == {"1861", "1862"}
    assert list(data["books"]["1861"]["volumes"]) == ["100"]
    assert list(data["books"]["1862"]["volumes"]) == ["200"]


# ── median_chars ──

def test_median_chars_none_without_records(tmp_path):
    assert manifest.median_chars(manifest.empty(), "1861") is None


def test_median_chars_ignores_non_complete(tmp_path):
    data = manifest.empty()
    book = manifest.get_book(data, "1861")
    book["volumes"] = {
        "1": {"chars": 100, "status": "complete"},
        "2": {"chars": 300, "status": "complete"},
        "3": {"chars": 5, "status": "suspect"},
    }
    assert manifest.median_chars(data, "1861") == 200


# ── rebuild_from_files ──

def test_rebuild_records_existing_files_as_unknown_script(tmp_path):
    out = str(tmp_path)
    vols = [_vol(100, 1, "第一卷"), _vol(200, 2, "第二卷")]
    build_path = _build_path_fn(out)
    _write(build_path(vols[0]))   # 只有第一卷落地

    data = manifest.rebuild_from_files(out, "1861", "書", vols, build_path)
    records = data["books"]["1861"]["volumes"]
    assert list(records) == ["100"]
    assert records["100"]["script"] == manifest.SCRIPT_UNKNOWN
    assert records["100"]["downloaded_at"]      # 取自檔案 mtime


def test_rebuild_does_not_overwrite_existing_records(tmp_path):
    out = str(tmp_path)
    vol = _vol(100)
    build_path = _build_path_fn(out)
    _write(build_path(vol))
    manifest.record_volume(out, "1861", "書", vol, build_path(vol), COMPLETE,
                           manifest.SCRIPT_TRADITIONAL)
    manifest.rebuild_from_files(out, "1861", "書", [vol], build_path)
    rec = manifest.load(out)["books"]["1861"]["volumes"]["100"]
    assert rec["script"] == manifest.SCRIPT_TRADITIONAL


# ── plan_update ──

def _planned(out, vols, book, want_script=manifest.SCRIPT_TRADITIONAL):
    return manifest.plan_update(vols, book, _build_path_fn(out), want_script)


def _group_of(plan, vid):
    for group, vols in plan.items():
        if any(v["vid"] == vid for v in vols):
            return group
    return None


def test_plan_new_when_no_record_and_no_file(tmp_path):
    vol = _vol(100)
    plan = _planned(str(tmp_path), [vol], {})
    assert _group_of(plan, 100) == "new"


def test_plan_incomplete_when_record_exists_but_file_gone(tmp_path):
    out = str(tmp_path)
    vol = _vol(100)
    build_path = _build_path_fn(out)
    _write(build_path(vol))
    manifest.record_volume(out, "1861", "書", vol, build_path(vol), COMPLETE,
                           manifest.SCRIPT_TRADITIONAL)
    os.remove(build_path(vol))
    book = manifest.load(out)["books"]["1861"]
    assert _group_of(_planned(out, [vol], book), 100) == "incomplete"


def test_plan_ok_when_size_matches(tmp_path):
    out = str(tmp_path)
    vol = _vol(100)
    build_path = _build_path_fn(out)
    _write(build_path(vol))
    manifest.record_volume(out, "1861", "書", vol, build_path(vol), COMPLETE,
                           manifest.SCRIPT_TRADITIONAL)
    book = manifest.load(out)["books"]["1861"]
    assert _group_of(_planned(out, [vol], book), 100) == "ok"


def test_plan_changed_when_size_differs(tmp_path):
    out = str(tmp_path)
    vol = _vol(100)
    build_path = _build_path_fn(out)
    _write(build_path(vol))
    manifest.record_volume(out, "1861", "書", vol, build_path(vol), COMPLETE,
                           manifest.SCRIPT_TRADITIONAL)
    _write(build_path(vol), chars=12345)    # 外部改過
    book = manifest.load(out)["books"]["1861"]
    assert _group_of(_planned(out, [vol], book), 100) == "changed"


def test_plan_chapters_changed_when_cids_differ(tmp_path):
    out = str(tmp_path)
    vol = _vol(100, cids=(1, 2, 3))
    build_path = _build_path_fn(out)
    _write(build_path(vol))
    manifest.record_volume(out, "1861", "書", vol, build_path(vol), COMPLETE,
                           manifest.SCRIPT_TRADITIONAL)
    book = manifest.load(out)["books"]["1861"]
    grown = _vol(100, cids=(1, 2, 3, 4))    # 站方補了一章
    assert _group_of(_planned(out, [grown], book), 100) == "chapters_changed"


def test_plan_script_mismatch(tmp_path):
    out = str(tmp_path)
    vol = _vol(100)
    build_path = _build_path_fn(out)
    _write(build_path(vol))
    manifest.record_volume(out, "1861", "書", vol, build_path(vol), COMPLETE,
                           manifest.SCRIPT_SIMPLIFIED)
    book = manifest.load(out)["books"]["1861"]
    plan = _planned(out, [vol], book, manifest.SCRIPT_TRADITIONAL)
    assert _group_of(plan, 100) == "script_mismatch"


def test_plan_unknown_script_does_not_trigger_redownload(tmp_path):
    out = str(tmp_path)
    vol = _vol(100)
    build_path = _build_path_fn(out)
    _write(build_path(vol))
    manifest.rebuild_from_files(out, "1861", "書", [vol], build_path)
    book = manifest.load(out)["books"]["1861"]
    plan = _planned(out, [vol], book, manifest.SCRIPT_TRADITIONAL)
    assert _group_of(plan, 100) != "script_mismatch"


def test_plan_puts_each_volume_in_exactly_one_group(tmp_path):
    out = str(tmp_path)
    vols = [_vol(100, 1, "甲"), _vol(200, 2, "乙"), _vol(300, 3, "丙")]
    build_path = _build_path_fn(out)
    _write(build_path(vols[0]))
    manifest.record_volume(out, "1861", "書", vols[0], build_path(vols[0]),
                           COMPLETE, manifest.SCRIPT_TRADITIONAL)
    book = manifest.load(out)["books"]["1861"]
    plan = _planned(out, vols, book)
    assert sum(len(v) for v in plan.values()) == len(vols)
    assert set(plan) == set(manifest.PLAN_GROUPS)


# ── 書本層級來源資訊 ──

URL = "https://www.wenku8.net/novel/1/1832/index.htm"


def test_record_book_meta_stores_aid_and_url(tmp_path):
    out = str(tmp_path)
    manifest.record_book_meta(out, "1832", "測試書名", URL)
    book = manifest.load(out)["books"]["1832"]
    assert book["aid"] == "1832"
    assert book["book_name"] == "測試書名"
    assert book["source_url"] == URL


def test_record_book_meta_does_not_clear_url_when_omitted(tmp_path):
    """後續的下載/修復流程不知道網址，不能把先前記好的洗掉。"""
    out = str(tmp_path)
    manifest.record_book_meta(out, "1832", "測試書名", URL)
    manifest.record_book_meta(out, "1832", "測試書名")      # 沒帶網址
    assert manifest.load(out)["books"]["1832"]["source_url"] == URL


def test_record_volume_keeps_source_url(tmp_path):
    out = str(tmp_path)
    manifest.record_book_meta(out, "1832", "測試書名", URL)
    vol = _vol(100)
    path = os.path.join(out, "01 第一卷.txt")
    _write(path)
    manifest.record_volume(out, "1832", "測試書名", vol, path, COMPLETE,
                           manifest.SCRIPT_TRADITIONAL)
    book = manifest.load(out)["books"]["1832"]
    assert book["source_url"] == URL
    assert book["aid"] == "1832"
    assert "100" in book["volumes"]


def test_two_books_keep_separate_urls(tmp_path):
    out = str(tmp_path)
    manifest.record_book_meta(out, "1832", "甲書", URL)
    manifest.record_book_meta(out, "1861", "乙書", "https://example.invalid/1861")
    books = manifest.load(out)["books"]
    assert books["1832"]["source_url"] == URL
    assert books["1861"]["source_url"] == "https://example.invalid/1861"
