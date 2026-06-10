import os
import queue

from opencc import OpenCC

_cc = OpenCC("s2twp")


def convert_to_traditional(text: str) -> str:
    return _cc.convert(text)


def run_convert_all(
    files: list[str], output_mode: str, msg_queue: queue.Queue
) -> None:
    success = 0
    fail = 0
    for filepath in files:
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                text = f.read()
            converted = convert_to_traditional(text)
            if output_mode == "overwrite":
                out_path = filepath
            else:
                base, ext = os.path.splitext(filepath)
                out_path = base + "_TC" + ext
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(converted)
            success += 1
            msg_queue.put(("conv_log", True, os.path.basename(filepath), ""))
        except Exception as e:
            fail += 1
            msg_queue.put(("conv_log", False, os.path.basename(filepath), str(e)))
    msg_queue.put(("conv_done", success, fail))
