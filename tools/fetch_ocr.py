"""Download the ppocr_v6/small OCR model into assets/maa/model/ocr (gitignored).

Same files, same pinned MaaCommonAssets commit as maalc's tools/fetch_ocr.py; only the target differs, since lc-helper
loads `assets/maa` as its resource bundle (ocr.py). The model is PaddleOCR (Apache-2.0).
"""

from pathlib import Path
from urllib.request import urlretrieve

COMMIT = "dabcd4681ac990dc4361de26416d986abd80e4aa"
BASE = f"https://raw.githubusercontent.com/MaaXYZ/MaaCommonAssets/{COMMIT}/OCR/ppocr_v6/small"
FILES = ["det.onnx", "rec.onnx", "keys.txt"]

ocr_dir = Path(__file__).resolve().parent.parent / "assets/maa/model/ocr"

if __name__ == "__main__":
    ocr_dir.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        if (ocr_dir / name).exists():
            print(f"skip {name}")
            continue
        print(f"fetch {name}")
        urlretrieve(f"{BASE}/{name}", ocr_dir / f"{name}.part")
        (ocr_dir / f"{name}.part").rename(ocr_dir / name)
