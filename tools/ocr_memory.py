"""What the OCR model costs in memory, and what dropping it gives back: three rounds of read the story box of maalc's
EventChoices.png capture, then ocr.release(), with private memory after each step. No window, no emulator.

Usage: uv run --group sync python tools/ocr_memory.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lc_helper import ocr, vision  # noqa: E402
from measure_memory import memory_mb  # noqa: E402
from sync_maalc import maalc_dir  # noqa: E402


def mark(step):
    private, ws = memory_mb()
    print(f"{step:<28} private {private:6.0f} MB   working set {ws:5.0f} MB", flush=True)


def main():
    image = vision.imread(maalc_dir() / "tests/screens/EventChoices.png")
    mark("start")
    for round_ in range(1, 4):
        t = time.perf_counter()
        ocr.lines(image, vision.EVENT_STORY)
        mark(f"round {round_}: read ({time.perf_counter() - t:.2f} s)")
        ocr.release()
        time.sleep(1)
        mark(f"round {round_}: released")


if __name__ == "__main__":
    main()
