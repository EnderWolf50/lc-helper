# lc-helper

Limbus Company 的浮動小工具：一個跟著遊戲的小視窗，放在 MuMu 模擬器或 PC（Steam）版旁邊用。遊戲到最前面時，它也在遊戲上面；切到別的程式時，它和遊戲一起被蓋住。

- **自動戰鬥**：每回合按 Win Rate（勝率）或 Damage（傷害），再按 START；回合播放時按住畫面角落，讓 E.G.O 動畫快轉。
- **戰鬥結束**：認得勝利（VICTORY）和全滅，記進戰鬥紀錄（齒輪設定頁「戰鬥」區的「戰鬥紀錄…」，每場回合數與時間），可以跳 Windows 通知，也可以設成勝利後停止自動戰鬥。
- **防禦**：戰鬥列的防禦選單選「不防禦」「防禦前幾回合」（旁邊填回合數，戰鬥中跟著倒數）或「全程防禦」；前幾回合用完接著自動戰鬥。專注戰鬥沒有防禦鏈，那回合改用自動選技能，防禦回合數保留到下一場。
- **鏡牢事件**：在事件選項頁按「讀取」（F9；旁邊的「自動」開著時，畫面出現就讀），或在同一排的搜尋框輸入記得的中英文字（繁體、簡體都可以；按框裡左邊的放大鏡或 Enter，打字停一下也會查），結果從搜尋框下拉，選一個才顯示；清空搜尋框，顯示的事件也清掉。從畫面讀到的事件（自動讀取或按「讀取」），遊戲離開選項頁時也清掉；搜尋來的事件留著。列出每個選項的效果：給什麼飾品、判定成功或失敗的結果、機率分支、後續頁。英文版和裝了都市零漢化（LLC，簡體）的遊戲都讀得到：畫面上漢字比英文字母多，就拿漢化組的簡體原文比對，否則照舊比英文。
- **自動跳過劇情**：在事件頁按亮著的 SKIP、Proceed、Continue，到選項頁、判定選罪人、Commence 時停下來給你決定。不會為了推進文字去點畫面：文字要點才會往下時，狀態寫「文字還在跑：點一下畫面讓它往下，按鈕亮了我來按」，由你點。只在認得出事件按鈕時動作。漢化版（LLC）的「继续」也會按，「进行判定」不按，「选项」與「选择一位罪人」停下。它只點亮著的按鈕和判定卡：PC 版每點一下，移視窗會把遊戲視窗移到游標下、合成觸控會藏起游標，所以不反覆點。
- **飾品**：飾品區有自己的搜尋框（中英文名字，繁體、簡體都可以），顯示中文效果、強化後效果、融合配方；每個飾品左邊是遊戲裡的飾品圖，名字前面是體系圖示（無體系的是一個灰色小圈），飾品之間有分隔線；搜尋結果每一列是飾品圖，右下角帶體系圖示，列與列之間有分隔線。自動讀取或 F9 遇到戰後選飾品頁、Boss 獎勵頁、GET! 視窗時，在飾品區列出畫面上每個飾品的中文效果，事件區的內容不動；漢化版（LLC）畫面上的簡體飾品名也認得。
- **選項推薦**：事件區「推薦體系（依順序）」用「＋ 體系」加一到四個體系。每個體系標籤是遊戲裡的體系圖示加中文名，越左邊越優先，標籤之間有箭頭；點標籤可以往前、往後移或移除。照 maalc 的排序在建議的選項標 ★（面板和遊戲內提示都有）：隨機（???）> 直接獲得飾品 > 判定通過獲得 > 依後續選擇獲得 > 其他；同一層裡，給排越前面體系飾品的選項越優先，體系不會讓選項跨層。灰掉（已經選過）的選項不推薦。
- **苦難評估**：打完一層的 Boss 後，選飾品頁每一欄是一個飾品配一個苦難（Mounting Trials，之後每個敵人都會帶著）。F9 或自動讀取讀到這一頁時，在遊戲上每一欄的上方放一張小卡片（不蓋到飾品和苦難）：排名與總分、算式「飾品 X − 苦難 Y」、苦難效果的中文。該選的欄（HARD 兩欄、普通一欄）有 ★「推薦」和金框。算法照 maalc：總分 = 飾品分 −（苦難分 + 0.36 × 敵人等級 +N）；飾品分是推薦體系的飾品 3、其他 2、已持有 0，每高一階 +0.5（已持有不加）；苦難分的單位是 pt，1 pt 約等於敵人拼點威力 +1，取自 maalc 的試煉表（資源包的 `trials.yaml`）。只畫在遊戲上，「遊戲內提示」關著時不顯示；離開這一頁就收起來。英文版與漢化版（LLC）的苦難名稱和效果都認得。
- **遊戲內提示**：讀到事件時，遊戲畫面上每個選項的左邊放一張卡片，和選項同高。卡片的樣子和配色跟 maalc 的設定視窗一樣：暖色深底、青銅框、切角。卡片平常是簡單版：判定看哪幾個罪孽（遊戲裡的罪孽圖示加名字），下面成功、失敗、機率各一個區塊，放飾品和效果，不寫名字和飾品效果。飾品畫成遊戲的飾品格（商店、Gift GET 頁用的那種）：黃黑斜紋底板，左上角是橘黃色的等級，右下角是體系圖示，位置和大小照遊戲。效果之間用「 · 」隔開，落在誰身上寫在那組效果前面，例如「判定的罪人 HP +30 · SP +30 · 其餘罪人 HP +12 · 開始戰鬥」。成功和增加是青綠色，失敗和減少是紅色。同一頁的飾品圖一樣大，放得下時三行字高，擠的時候兩行。卡片只有內容那麼寬，靠右貼著選項。點一下卡片就展開成詳細版，寫出每個飾品的名字、體系、等級和完整效果，蓋在其他卡片上面；再點一下收起來，點別張就換那張展開。推薦的選項有 ★ 和琥珀色框，展開中的卡片是奶油色框，選過的選項字變淡。只有卡片本身能點，卡片以外的地方點擊照樣給遊戲，點卡片也不會讓遊戲失去焦點；提示只在遊戲上面，切到別的程式時不會浮在那個程式上；離開選項頁就收起來，按「讀取」讀到的也一樣（讀到事件但不在選項頁時，60 秒後收起來）。捲動選項列表時，卡片跟著換成畫面上的選項，按「讀取」讀到的也一樣。

辨識與點擊的位置、等待時間都沿用 [maalc](https://github.com/EnderWolf50/maalc) 實機調過的數字；事件資料來自 maalc 的資源包，中文取自都市零漢化組（CC BY-NC-SA 4.0）。遊戲內容的著作權屬於 © Project Moon；各檔的來源、授權與修改見 [NOTICE.md](NOTICE.md)。程式碼採 PolyForm Noncommercial 1.0.0（[LICENSE](LICENSE)）。

## 執行

```powershell
uv sync
uv run python tools/fetch_resource.py   # 第一次，和換 resource.lock.json 的版本後：遊戲資料、圖、模板
uv run python tools/fetch_ocr.py        # 第一次：OCR 模型
uv run lc-helper
```

`uv run lc-helper` 開的視窗沒有主控台；要看錯誤輸出改用 `uv run python -m lc_helper`。

視窗：標題列有連線燈號與裝置名（例如 MuMu 0、PC 版、未連線）、齒輪、跟著遊戲、關閉。主畫面最上面是戰鬥列（勝率或傷害、防禦、開始鈕；開始鈕平常是綠色，戰鬥中變紅色的停止），下面是「鏡牢事件」與「飾品」兩區，按區塊標題各自收合，收合時標題寫重點（例如「自動讀取開 · 推薦 充能 › 流血」、「最近：地獄蝶之夢」），開合狀態會記住。新視窗只開鏡牢事件區。齒輪換到設定頁，再按一次回到主畫面。

熱鍵：F8 開始／停止自動戰鬥，F9 讀取畫面上的事件或飾品。設定（裝置、PC 版點擊方式與戰鬥解析度、勝率或傷害、防禦、推薦體系、熱鍵、字級、跟著遊戲、哪幾區開著、視窗位置）存在 `.local/settings.json`；舊版寫的設定檔開窗時自動換成新格式。熱鍵在齒輪設定頁「熱鍵」區按「修改…」改，可以加 Ctrl、Alt、Shift。

字級：齒輪設定頁「顯示」區的「字級」選小、標準（預設）、大；視窗與對話框的字一起變，視窗寬度跟著字放大。

視窗高度：事件區與飾品區的內容框跟著內容長高，沒有內容時只有三行高；太長時停在固定高度，多的在框裡捲動。視窗放得低時內容框會縮短，讓視窗底部留在螢幕裡，兩區都開時較長的先縮（最短三行）；視窗不會被移走，放在哪就在哪。

跟著遊戲：標題列齒輪右邊的圖釘按鈕。開著（預設）時，遊戲視窗到最前面（點遊戲、Alt+Tab、按工作列），lc-helper 的視窗也跟著到遊戲上面；切到別的程式時，它和遊戲一起被那個程式蓋住，不會一直擋在最上層。跟的是裝置選單選的那個（PC 版或那個 MuMu 實例）。關掉後是一般視窗，點遊戲時會被遊戲蓋住。兩種都佔工作列，被蓋住時從工作列或 Alt+Tab 叫回來。

PC 版：齒輪設定頁「裝置」區的裝置選單選「PC 版」。遊戲視窗開成什麼大小都連得上，不能縮到最小，可以在背景被別的視窗蓋住。點擊方式在同一區的「PC 點擊」，有移視窗（預設）、觸控、借游標、前景四種，滑過去會說明各自的代價。移視窗不動滑鼠，每次點擊時遊戲視窗瞬間移到游標下，點完移回原位。觸控要遊戲露出來，點擊位置被別的視窗蓋住時不會點下去。

PC 解析度：同一區的「PC 解析度」選自動功能開著時遊戲畫面的大小，預設 2560×1440，也可以選 1280×720、1600×900、1920×1080 或不調整。自動戰鬥、自動讀取、跳過劇情任一個開始時調整，全部關掉、換點擊方式或關掉 lc-helper 時還原原本的大小與位置。遊戲是全螢幕或最大化時不調整，狀態列會說原因。遊戲畫面不是 16:9 時讀不準，所以沒調整的話（選不調整、全螢幕或最大化），讀取和自動功能會停下來，狀態列說原因。

MaaFramework 的日誌：lc-helper.exe 預設不寫。要查問題時，把 `.local/maa/config/maa_option.json` 的 `logging` 改成 `true`，日誌寫在 `.local/maa/debug`，超過一週的 MaaFramework 會自己刪掉。從原始碼執行時預設會寫。

遊戲資料（事件、飾品、試煉與它們的中文）、飾品圖、體系圖示與戰鬥模板來自 maalc 的資源包，不需要 maalc 的 checkout。`resource.lock.json` 記著用哪一版（[maalc-resource](https://github.com/EnderWolf50/maalc-resource) 的 tag）；`tools/fetch_resource.py` 把那一版的 `manifest.json` 和 lc-helper 讀的檔下載到 `resource/`（gitignore），逐檔核對 manifest 的大小與 sha256，已經對的檔不重抓，中途失敗不留半個檔，所以可以重跑。換版本只改 `resource.lock.json` 的 `version` 再重跑。簡體原文留在 `_cn` 欄位（飾品是 `cn`），給漢化版畫面比對用；繁體由資源包轉好，lc-helper 不再轉換。OCR 模型不在資源包裡，由 `tools/fetch_ocr.py` 下載。資源包還帶著 `LICENSE` 與 `NOTICE.md`（在 maalc-resource 根目錄，不在 manifest 裡），`fetch_resource.py` 一併抓進 `resource/`，打包時跟著進 `dist`。`resource/` 的程式端讀寫在 `src/lc_helper/package.py`（`sync`、`manifest`、`path`），事件、飾品、試煉三本書由 `src/lc_helper/gamedata.py` 從資料檔組出來。

打包出來的 lc-helper 內附 lock 檔那一版。每次啟動（`--offline` 與 `--self-test` 除外）會讀 maalc-resource `main` 的最新 manifest（整個檢查最多 10 秒）：版本比手上的新，才下載有變動的檔到 `.local/resource/`，每個檔驗過 sha256 再整份換上；格式版本或模板版本不認得的那一部分跳過、保留原檔，另一部分照常套用。用哪一份：內附的和 `.local/resource/` 裡的，manifest 版本較新的那份，一樣新就用內附的。連不上、逾時（下載另算 60 秒）或檔案不符時，檔案不變，在 `.local/resource.log` 記一行原因。同時開著兩個 lc-helper 時，只有先開的那個（持有 `.local/resource.lock`）會檢查與換檔，後開的直接讀現有的那份。程式在 `src/lc_helper/startup.py`。

罪孽圖示與飾品格底板（資源包的 `data/sin_icons`、`data/gift_slot`）同樣來自資源包，由 maalc 的 `tools/sin_icons.py` 與 `tools/gift_slot.py` 從拆包的客戶端匯出，遊戲改版後在 maalc 重跑，lc-helper 只換 `resource.lock.json` 的版本。留在 repo 裡的只有字型和自己裁的 5 個模板。測試和 `tools/render_window.py` 等工具用的截圖是 maalc 的 `tests/screens`，從 maalc 的 checkout 讀（預設是本 repo 旁邊的 `../maalc`，不在那裡就把路徑寫進 `.local/maalc_dir`）（CI 抓 `.github/maalc-commit` 那個 commit 的 `tests/screens`）。

## 打包（免安裝資料夾）

```powershell
uv run --group build python tools/build.py   # 產生 dist/lc-helper/（要先跑兩支 fetch 工具），整個資料夾複製走就能用，不需要 uv 或 Python
uv run python tools/exe_check.py             # 打包版自我測試（事件搜尋、OCR），再用離線模式開一次視窗、截圖、關掉
```

`lc-helper.exe --offline` 不找也不連模擬器或 PC 版，只查事件。設定存在 exe 旁邊的 `.local/`。

## 檢查

```powershell
uv run pytest                       # 辨識、戰鬥流程、事件、背景執行緒；需要 maalc 的 tests/screens
uv run python tools/sweep_screens.py   # 每張截圖的辨識結果
uv run python tools/render_window.py   # 視窗各狀態的截圖，存到 .local/evidence
uv run python tools/overlay_preview.py            # 把遊戲內提示與苦難評估畫在 maalc 的截圖上（.local/evidence/overlay-*.png）
uv run python tools/launch_check.py                 # 真的開視窗、量啟動時間、切換跟著遊戲、送熱鍵，不碰模擬器
uv run python tools/pc_input_check.py touch         # PC 版點擊方式在自己的探測視窗上點、長按、拖曳，看游標有沒有動
uv run python tools/measure_memory.py               # 視窗出現 8 秒後的 private memory，不碰模擬器
uv run python tools/ocr_memory.py      # OCR 讀一次、釋放，各吃多少記憶體
bash tools/check_commits.sh                         # 逐一切到每個 commit 跑測試和 lint
```

CI（`.github/workflows/test.yml`）在 Windows 上跑 `pytest`：用 sparse checkout 抓 maalc 的 `tests/screens`，commit 記在 `.github/maalc-commit`（換 commit 只改那一行），先跑 `tools/fetch_resource.py` 抓資源包，OCR 模型由 `tools/fetch_ocr.py` 照 maalc 的來源下載。

## 授權

- 事件與飾品的中文文字：[都市零漢化組](https://github.com/LocalizeLimbusCompany/LocalizeLimbusCompany)，CC BY-NC-SA 4.0。
- 遊戲資料與圖像 © Project Moon；非官方粉絲作品。
- 移植自 maalc 的程式碼沿用 maalc 的授權（PolyForm Noncommercial 1.0.0）。
