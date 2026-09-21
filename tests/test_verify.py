"""verify.py 的單元測試。門檻數字的由來見 src/verify.py 的 docstring
（2026-09-21 對 aid=1861 第 1／21／57 卷的實測）。"""

from src.verify import (
    normalize,
    verify_volume,
    verify_file,
    ANCHOR_MIN_LEN,
    FALLBACK_CHARS_FLOOR,
)


def _chapters(*titles):
    return [{"cid": 1000 + i, "title": tt} for i, tt in enumerate(titles)]


def _body(anchor_titles, padding=2000, tail_padding=200):
    """組一段假內文：每個標題之間塞足夠的填充字，讓位置比例算得出來。"""
    parts = []
    for tt in anchor_titles:
        parts.append("　　" + tt + "\n")
        parts.append("內" * padding + "\n")
    parts.append("文" * tail_padding)
    return "".join(parts)


# ── normalize ──

def test_normalize_strips_all_whitespace_kinds():
    assert normalize("第一章 『開始』") == normalize("第一章　『開始』")
    assert normalize("a\tb\nc d") == "abcd"


def test_normalize_unifies_separator_variants():
    # 實測踩到的那一類：目錄與 txt 用了不同的間隔號
    variants = ["華麗•重裝", "華麗·重裝", "華麗・重裝", "華麗‧重裝"]
    assert len({normalize(v) for v in variants}) == 1


def test_normalize_unifies_bracket_variants():
    assert normalize("幕間『甲』") == normalize("幕間「甲」")


# ── 錨點門檻 ──

def test_short_titles_are_not_anchors():
    short = "插圖"
    assert len(short) < ANCHOR_MIN_LEN
    # 只有短標題 → 沒有錨點，退回字數判定（字數夠 → complete）
    result = verify_volume("正" * 9000, _chapters(short, "後記"))
    assert result["anchor_total"] == 0
    assert result["status"] == "complete"


def test_complete_all_anchors_hit():
    titles = ["序章 『起點』", "第一章 『途中』", "終章 『結尾』"]
    result = verify_volume(_body(titles), _chapters(*titles))
    assert result["status"] == "complete"
    assert result["anchor_hits"] == result["anchor_total"] == 3
    assert result["tail_position"] > 0.5


def test_complete_even_when_one_title_mismatches():
    """第 21 卷的實測樣態：一章標點對不上仍是完整檔，不可誤判。"""
    present = ["序章 『起點』", "第一章 『途中』", "第二章 『再來』",
               "第三章 『接著』", "終章 『結尾』"]
    catalog = present + ["幕間 『對不上的那章』"]
    result = verify_volume(_body(present), _chapters(*catalog))
    assert result["anchor_hits"] == 5
    assert result["anchor_total"] == 6
    assert result["status"] == "complete"


def test_suspect_when_too_many_anchors_missing():
    catalog = ["序章 『起點』", "第一章 『途中』", "第二章 『再來』",
               "第三章 『接著』", "終章 『結尾』"]
    result = verify_volume(_body(catalog[:2]), _chapters(*catalog))
    assert result["status"] == "suspect"
    assert result["reason"] == "anchor_ratio"


def test_suspect_when_tail_anchor_too_early():
    """斷檔的相反樣態：標題全在前段命中，後面接一大段沒有標題的內容。"""
    titles = ["序章 『起點』", "第一章 『途中』", "終章 『結尾』"]
    text = _body(titles, padding=100, tail_padding=0) + "尾" * 50000
    result = verify_volume(text, _chapters(*titles))
    assert result["status"] == "suspect"
    assert result["reason"] == "anchor_tail"


def test_garbled_beats_anchor_check():
    titles = ["序章 『起點』", "第一章 『途中』", "終章 『結尾』"]
    result = verify_volume(_body(titles) + "�", _chapters(*titles))
    assert result["status"] == "garbled"


# ── 無錨點時的字數 fallback ──

def test_fallback_uses_floor_when_no_median():
    assert verify_volume("字" * (FALLBACK_CHARS_FLOOR - 1), [])["status"] == "suspect"
    assert verify_volume("字" * FALLBACK_CHARS_FLOOR, [])["status"] == "complete"


def test_fallback_uses_median_when_available():
    # median 100000 → 門檻 20000，遠高於 3000 的下限
    result = verify_volume("字" * 10000, [], median_chars=100000)
    assert result["status"] == "suspect"
    assert result["reason"] == "too_short"
    assert verify_volume("字" * 30000, [], median_chars=100000)["status"] == "complete"


# ── verify_file ──

def test_verify_file_missing_returns_none(tmp_path):
    assert verify_file(str(tmp_path / "nope.txt")) is None


def test_verify_file_reads_and_verifies(tmp_path):
    titles = ["序章 『起點』", "第一章 『途中』", "終章 『結尾』"]
    path = tmp_path / "vol.txt"
    path.write_text(_body(titles), encoding="utf-8")
    assert verify_file(str(path), _chapters(*titles))["status"] == "complete"


def test_verify_file_non_utf8_is_garbled(tmp_path):
    path = tmp_path / "old.txt"
    path.write_bytes("中文內容".encode("big5"))
    assert verify_file(str(path))["status"] == "garbled"


# ── 錨點數量不足（實測 aid=1832 打出來的洞）──

def test_single_anchor_at_file_start_is_not_treated_as_truncation():
    """光禿標題的書只剩 1 個錨點（例如卷首的「主要人物」），它必然在檔頭。

    拿它跑 tail 測試會判成斷檔，但檔案是完整的。錨點不足就不該採信位置資訊。
    """
    catalog = ["主要人物", "序章", "第一章", "第二章", "終章", "後記", "插圖"]
    text = "　　主要人物\n" + "內" * 150000
    result = verify_volume(text, _chapters(*catalog))
    assert result["status"] == "complete"
    assert result["anchor_total"] == 0      # 不足門檻，不採計


def test_two_anchors_still_fall_back_to_char_count():
    titles = ["序章 『起點』", "終章 『結尾』"]
    text = _body(titles, padding=100, tail_padding=0) + "尾" * 50000
    assert verify_volume(text, _chapters(*titles))["status"] == "complete"


def test_three_anchors_do_use_the_tail_check():
    """剛好到門檻就要恢復嚴格判定，否則斷檔又驗不出來。"""
    titles = ["序章 『起點』", "第一章 『途中』", "終章 『結尾』"]
    text = _body(titles, padding=100, tail_padding=0) + "尾" * 50000
    result = verify_volume(text, _chapters(*titles))
    assert result["status"] == "suspect"
    assert result["reason"] == "anchor_tail"
