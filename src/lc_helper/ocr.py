"""Text on a screenshot through MaaFramework's OCR (maalc's ppocr_v6 model in assets/maa/model/ocr).

The recogniser gets its own tasker on a blank controller: it reads the image it is handed, so OCR works with or
without an emulator and never waits on the device's screenshots or taps. Loading takes ~1 s: the first read pays it.
"""

import threading

from .vision import ASSETS, crop

_lock = threading.Lock()
_tasker = None


def _blank_controller():
    import numpy as np
    from maa.controller import CustomController

    class Blank(CustomController):
        def connect(self):
            return True

        def request_uuid(self):
            return "lc-helper-ocr"

        def screencap(self):
            return np.zeros((720, 1280, 3), np.uint8)

        def __getattr__(self, name):  # taps, swipes, keys: there is no screen behind it
            return lambda *a, **k: True

    return Blank()


def _get():
    global _tasker
    with _lock:
        if _tasker is None:
            from maa.resource import Resource
            from maa.tasker import Tasker

            if not (ASSETS / "maa/model/ocr/rec.onnx").is_file():
                raise RuntimeError("沒有 OCR 模型：執行 uv run --group sync python tools/sync_maalc.py")
            Tasker.set_log_dir(str(ASSETS.parent / ".local/maa"))
            Tasker.set_stdout_level(0)
            Tasker.set_save_draw(False)
            res = Resource()
            res.post_bundle(str(ASSETS / "maa")).wait()
            ctl = _blank_controller()
            ctl.post_connection().wait()
            tasker = Tasker()
            tasker.bind(res, ctl)
            _tasker = (tasker, res, ctl)
        return _tasker[0]


def lines(image, roi, only_rec=False):
    """Every text line in roi as (text, (x, y, w, h)), top to bottom; only_rec reads roi as one line."""
    from maa.pipeline import JOCR

    if crop(image, roi).size == 0:
        return []
    detail = _get().post_recognition("OCR", JOCR(roi=list(roi), only_rec=only_rec), image).wait().get()
    results = []
    for node in detail.nodes if detail else []:
        reco = node.recognition
        for r in (reco.all_results if reco else []):
            results.append((r.text, tuple(r.box)))
    return sorted(results, key=lambda r: (r[1][1], r[1][0]))


def warm():
    """Load the model and run it once now (from a worker thread): the first read pays ~1.5 s of session setup."""
    import numpy as np

    lines(np.zeros((720, 1280, 3), np.uint8), (0, 0, 200, 60))
