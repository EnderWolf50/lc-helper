# lc-helper

Limbus Company 的浮動小工具：一個置頂的小視窗，放在 MuMu 模擬器或 PC（Steam）版旁邊用。

- **自動戰鬥**：每回合按 Win Rate 或 Damage，再按 START；回合播放時按住畫面角落，讓 E.G.O 動畫快轉。
- **戰鬥結束**：認得勝利（VICTORY）和全滅，記進戰鬥紀錄（「⋯」→「戰鬥紀錄」，每場回合數與時間），可以跳 Windows 通知，也可以設成勝利後停止自動戰鬥。
- **防禦回合**：先防禦指定回合數（或無限防禦），用完接著自動戰鬥。專注戰鬥沒有防禦鏈，那回合改用自動選技能，防禦回合數保留到下一場。
- **鏡牢事件**：在事件選項頁按「讀取畫面」（或開自動讀取），或輸入記得的中英文字，列出每個選項的效果：給什麼飾品、判定成功或失敗的結果、機率分支、後續頁。
- **自動跳過劇情**：在事件頁按亮著的 SKIP、Proceed、Continue，文字還在跑就點左上角推進；到選項頁、判定選罪人、Commence 時停下來給你決定。只在認得出事件按鈕時動作。
- **疊加顯示**：讀到事件時，把每個選項的效果標在遊戲畫面上那個選項的左邊。點擊會穿過去，不擋操作；自動讀取開著時，離開選項頁就收起來，手動讀取的停留 60 秒。

辨識與點擊的位置、等待時間都沿用 [maalc](../maalc) 實機調過的數字；事件資料來自 maalc 的事件表，中文取自都市零漢化組。

## 執行

```powershell
uv sync
uv run --group sync python tools/sync_maalc.py   # 第一次，和每季 maalc 更新事件表後
uv run lc-helper
```

`uv run lc-helper` 開的視窗沒有主控台；要看錯誤輸出改用 `uv run python -m lc_helper`。

熱鍵：F8 開始／停止自動戰鬥，F9 讀取畫面上的事件。設定（模擬器或 PC 版、PC 版點擊方式、勝率或傷害、防禦回合、熱鍵、視窗位置）存在 `.local/settings.json`。熱鍵在「⋯」→「熱鍵設定」改，可以加 Ctrl、Alt、Shift。

PC 版：裝置選單裡選「Limbus PC」。遊戲視窗要 16:9（1280×720 或 1920×1080），不能縮到最小，可以被別的視窗蓋住。點擊方式在「⋯」選單的「PC 版點擊方式」，預設「合成觸控」不動滑鼠；遊戲不吃觸控的話改「移動視窗」，再不行改「借用游標」。小工具不要擋在遊戲視窗上面：合成觸控點到被蓋住的地方時，會把遊戲視窗暫時提到最上層。

`tools/sync_maalc.py` 從 maalc 的資料夾讀資料：預設是本 repo 旁邊的 `../maalc`，不在那裡就把路徑寫進 `.local/maalc_dir`。事件的完整英文故事與中文文字要 maalc 的 `.local/unpack` 與 `.local/llc`。

## 打包（免安裝資料夾）

```powershell
uv run --group build python tools/build.py   # 產生 dist/lc-helper/，整個資料夾複製走就能用，不需要 uv 或 Python
uv run python tools/exe_check.py             # 打包版自我測試（事件搜尋、OCR），再用離線模式開一次視窗、截圖、關掉
```

`lc-helper.exe --offline` 不找也不連模擬器或 PC 版，只查事件。設定存在 exe 旁邊的 `.local/`。

## 檢查

```powershell
uv run --group sync pytest          # 辨識、戰鬥流程、事件、背景執行緒；需要 maalc 的 tests/screens
uv run --group sync python tools/sweep_screens.py   # 每張截圖的辨識結果
uv run --group sync python tools/render_window.py   # 視窗各狀態的截圖，存到 .local/evidence
uv run python tools/launch_check.py                 # 真的開視窗、量啟動時間、送熱鍵，不碰模擬器
uv run python tools/pc_input_check.py touch         # PC 版點擊方式在自己的探測視窗上點、長按、拖曳，看游標有沒有動
uv run python tools/measure_memory.py               # 視窗出現 8 秒後的 private memory，不碰模擬器
uv run --group sync python tools/ocr_memory.py      # OCR 讀一次、釋放，各吃多少記憶體
bash tools/check_commits.sh                         # 逐一切到每個 commit 跑測試和 lint
```

## 授權

- 事件與飾品的中文文字：[都市零漢化組](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany)，CC BY-NC-SA 4.0。
- 遊戲資料與圖像 © Project Moon；非官方粉絲作品。
- 移植自 maalc 的程式碼沿用 maalc 的授權（PolyForm Noncommercial 1.0.0）。
