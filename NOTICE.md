# 第三方內容與授權

lc-helper 的程式碼採 [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)（`LICENSE`）。沿用 [maalc](https://github.com/EnderWolf50/maalc) 的辨識位置、等待時間與試煉算法，maalc 也以同一授權發佈，所以 `LICENSE` 開頭同時列出兩個專案的 `Required Notice`。

遊戲資料、圖與中文文字經 maalc 的資源包（[maalc-resource](https://github.com/EnderWolf50/maalc-resource)）取得：`tools/fetch_resource.py` 照 `resource.lock.json` 的版本抓到 `resource/`（不放進 repo；打包的資料夾內附 `resource/` 的檔案）。那些內容的來源、授權與修改，以資源包附的 NOTICE 為準：[maalc-resource 的 NOTICE.md](https://github.com/EnderWolf50/maalc-resource/blob/main/NOTICE.md)，換版本時看 `resource.lock.json` 那個 tag 的同一個檔。

## Limbus Company 遊戲內容

lc-helper 讀的遊戲資料、圖與模板在資源包裡，著作權屬於 © Project Moon，不在本專案的授權範圍內，來源與修改見資源包的 NOTICE.md「Limbus Company 遊戲素材」與「觀測飾品與合成飾品的資料」兩節：

- `resource/data/` 的事件表、飾品表、試煉表與事件、飾品、試煉的文字（`event_table.json`、`event_text.json`、`gift_text.json`、`gift_recipes.json`、`trials.yaml`、`trial_text.json`）。
- `resource/data/gift_icons/` 的飾品圖、`resource/data/keyword_icons/` 的體系圖示。
- `resource/image/` 與 `resource/data/stagger_word.png` 的 8 個戰鬥與事件模板。

下列檔案留在本 repo，同樣是 © Project Moon，不在本專案的授權範圍內：

- `assets/sin_icons/` 的 7 個罪孽圖示：`tools/sin_icons.py` 從客戶端 1.118.1 的 `UISpriteDataManager`（`totalAttributeSpriteList`，精靈圖 `BattleUI_Choice 1_<顏色>`）匯出。
- `assets/gift_slot/plate.png` 的飾品格底板：`tools/gift_slot.py` 從客戶端 1.118.1 的 Legacy 主題圖集 `EgoGift` 匯出（`EgoGift_bg1`）。
- `assets/templates/` 的 5 個模板（`battle_turn_llc*.png`、`victory.png`、`wipe_text.png`）與 `tests/screens_llc/` 的測試截圖：裁自遊戲畫面。

## 都市零漢化組（LLC）的中文名稱與效果文字

事件的故事與選項文字、飾品名稱與效果、試煉名稱與效果的中文，取自 [都市零漢化組（Localize Limbus Company，LLC）](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany) 的簡體中文在地化，採 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)（非商用、姓名標示、相同方式共享）授權。它們在資源包的 `event_text.json`、`gift_text.json`、`trial_text.json`；使用的 LLC release、取用的欄位與修改（去掉標記、`[狀態]` 換成狀態名稱、OpenCC `s2twp` 轉繁體再改五個用詞），見資源包 NOTICE.md「都市零漢化組（LLC）的中文名稱與效果文字」一節，release 也寫在這三個檔的 `zh_release`。lc-helper 不再轉換文字：各檔以 `_cn` 或 `cn` 結尾的欄位是 LLC 的簡體原文，以 `_zh` 或 `zh` 結尾的是資源包轉好的繁體。

## 字型

`assets/fonts/barlow-condensed/` 的 Barlow Condensed（600、700 字重）是 Copyright 2017 The Barlow Project Authors，採 [SIL Open Font License 1.1](https://openfontlicense.org/)，授權全文在同一資料夾的 `LICENSE`。取自 `@fontsource/barlow-condensed` 的 WOFF，轉成 TrueType 後放進 repo，字型內容沒有修改。字型不是遊戲素材，不在資源包裡。

## 打包的 lc-helper 內附的第三方程式

`tools/build.py` 組出的 `dist/lc-helper/` 另外附上：

- OCR 模型 ppocr_v6/small（`assets/maa/model/ocr/`），取自 [MaaCommonAssets](https://github.com/MaaXYZ/MaaCommonAssets/tree/main/OCR/ppocr_v6/small)，出自 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) 的 PP-OCRv6，採 [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) 授權。
- [MaaFramework](https://github.com/MaaXYZ/MaaFramework)（`maafw` 套件），採 LGPL-3.0 授權。
- [PySide6](https://doc.qt.io/qtforpython-6/) 與它附的 Qt，採 LGPL-3.0 授權。
- [Python](https://www.python.org/) 的執行環境，採 PSF License；由 [PyInstaller](https://pyinstaller.org/) 打包。
