# 第三方內容與授權

lc-helper 的資料與圖大多取自 [maalc](https://github.com/EnderWolf50/maalc)，來源與授權照 maalc 的 [NOTICE.md](https://github.com/EnderWolf50/maalc/blob/main/NOTICE.md) 整理如下。

## Limbus Company 遊戲內容

下列檔案取自 Limbus Company，著作權屬於 © Project Moon，不在本專案的授權範圍內：

- `assets/events.json`、`assets/gifts.json`、`assets/trials.json` 的 id、英文名稱與文字、數值：取自遊戲客戶端 1.118.1 的靜態資料與英文在地化，經 maalc 的事件表、飾品表與試煉表整理；試煉分是 maalc 算的。
- `assets/gift_icons/` 的飾品圖：遊戲的 `Sprite/EgoGiftIcon`，取自 maalc 的 `gift_icons/`。
- `assets/keywords/` 的體系圖示：取自 maalc 的 `keyword_icons/`，轉成 PNG。
- `assets/sin_icons/` 的 7 個罪孽圖示：`tools/sin_icons.py` 從客戶端 1.118.1 的 `UISpriteDataManager`（`totalAttributeSpriteList`，精靈圖 `BattleUI_Choice 1_<顏色>`）匯出。
- `assets/gift_slot/plate.png` 的飾品格底板：`tools/gift_slot.py` 從客戶端 1.118.1 的 Legacy 主題圖集 `EgoGift` 匯出（`EgoGift_bg1`）。
- `assets/templates/` 的模板與 `tests/screens_llc/` 的測試截圖：裁自遊戲畫面，多數取自 maalc 的模板。

## 都市零漢化組（LLC）的中文名稱與效果文字

中文取自 [都市零漢化組（Localize Limbus Company，LLC）](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany) 的簡體中文在地化，版權屬於 Copyright (c) 2024 to now Localize Limbus Company 與其貢獻者，採 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)（非商用、姓名標示、相同方式共享）授權。本專案使用 release [2026110501](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany/releases/tag/2026110501)（2026-11-05）的內容，記在 `assets/events.json` 的 `zh_release`：

- `assets/events.json`：事件的故事與選項文字、選項給的飾品名稱。
- `assets/gifts.json`：飾品名稱、效果與強化後效果。
- `assets/trials.json`：試煉名稱與效果。

各檔中以 `_cn` 或 `cn` 結尾的欄位是 LLC 的簡體原文，以 `_zh` 或 `zh` 結尾的是轉換後的繁體。

修改：去掉文字裡的標記，飾品效果的 `[狀態]` 換成狀態名稱；以 OpenCC `s2twp` 由簡體轉成繁體，再改五個用詞（「指標」改回「指針」、「重新整理」改回「刷新」、「映象」改為「鏡像」、「透過階層」改為「通過階層」、「松肉」改為「鬆肉」）。轉換由 `tools/sync_maalc.py` 完成。這三個檔的中文名稱與文字同樣以 CC BY-NC-SA 4.0 授權；檔內的 id、英文與數值仍是 © Project Moon。

## 字型

`assets/fonts/barlow-condensed/` 的 Barlow Condensed（600、700 字重）是 Copyright 2017 The Barlow Project Authors，採 [SIL Open Font License 1.1](https://openfontlicense.org/)，授權全文在同一資料夾的 `LICENSE`。由 `tools/sync_maalc.py` 從 `@fontsource/barlow-condensed` 的 WOFF 轉成 TrueType，字型內容沒有修改。

## 打包的 lc-helper 內附的第三方程式

`tools/build.py` 組出的 `dist/lc-helper/` 另外附上：

- OCR 模型 ppocr_v6/small（`assets/maa/model/ocr/`），取自 [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets/tree/main/OCR/ppocr_v6/small)，出自 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) 的 PP-OCRv6，採 [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) 授權。
- [MaaFramework](https://github.com/MaaXYZ/MaaFramework)（`maafw` 套件），採 LGPL-3.0 授權。
- [PySide6](https://doc.qt.io/qtforpython-6/) 與它附的 Qt，採 LGPL-3.0 授權。
- [Python](https://www.python.org/) 的執行環境，採 PSF License；由 [PyInstaller](https://pyinstaller.org/) 打包。
