# VideoTextExtractor 🎥📄

[English](#english) | [繁體中文](#繁體中文)

---

<a id="english"></a>
## 🇬🇧 English

A powerful GUI tool that extracts every single word from YouTube videos using advanced OCR technology. It preserves the original visual grouping, meaning text on the same horizontal line on-screen stays on the same line in your output file!

> ⚠️ **Note**: This is NOT a subtitle downloader. It actively scans the visual frames of the video to extract burned-in text, titles, presentations, game UIs, watermarks, etc.

### Core Features
- **Batch Processing**: Queue up to 5 YouTube URLs at once.
- **Smart Row-Clustering**: Intelligently groups text bounding boxes. Words appearing on the same horizontal plane in the video are naturally output on the same line in the text file.
- **Precise Timestamps**: Every line of text is prefixed with the exact time `[HH:MM:SS]` it appeared on screen.
- **Language Optimizer**: Switch between "Mixed (Zh/En)", "English Only", or "Chinese Only" to drastically reduce false positive OCR detections.
- **🚀 High-Accuracy Mode (Triple-Pass OCR)**:
  - Specially designed for extreme edge cases like screen-filling hollow titles or tiny footnote texts.
  - Automatically runs 3 simultaneous passes (`1.5x zoom` for tiny text, `0.7x zoom`, and `0.3x extreme shrink` with morphological bridging) to ensure the AI never misses a massive title card!

### Installation & Usage

**Method 1: Standalone Executable (Recommended)**
1. Go to the **Releases** section on the right side of this GitHub repository.
2. Download the latest executable file (.exe).
3. Double-click `VideoTextExtractor.exe` to launch the GUI. No installation or Python environments required!

**Method 2: Run from Source**
1. Install Python 3.8+
2. Install the required dependencies:
   ```cmd
   pip install -r requirements.txt
   ```
3. Run the main script:
   ```cmd
   python video_text_extractor_gui.py
   ```
*(Note: Requires FFmpeg installed and in your system PATH for `yt-dlp` to properly download video/audio streams).*

### Output Example
```text
==================================================
  YouTube Video Text Extractor
  YouTube Video Text Extraction Results
==================================================

Video Title: Youtube Video Title
Video URL: https://www.youtube.com/watch?v=xxxxx
Video Duration: 00:03:15

--------------------------------------------------

[00:00:01] Text
[00:00:05] Text
[00:00:10] Text
[00:00:15] Text

--------------------------------------------------
```

---

<a id="繁體中文"></a>
## 🇹🇼 繁體中文

這是一個具有圖形化介面 (GUI) 的實用工具，能透過進階 OCR 技術從 YouTube 影片中擷取畫面上出現的所有文字。它能智慧還原視覺排版，在畫面上處於「同一水平線」的文字，在輸出的純文字檔中也會精準對齊在同一行！

> ⚠️ **注意**：這不是單純的內建字幕下載工具。程式會直接掃描「影片畫面本身」，辨識任何出現在畫面上的文字（例如簡報大綱、遊戲實況字體、特效標題、浮水印等）。

### 核心功能
- **批次處理支援**：可同時輸入最多 5 個 YouTube 網址排隊處理。
- **智慧多行分段 (Row-Clustering)**：自動分析文字框的座標高度。同一橫列的文字會排在同一行，不同段落的文字會自動分段。
- **精準時間戳記**：提取出的每一行文字前，都會清晰標示該畫面出現的 `[HH:MM:SS]` 時間。
- **語言最佳化引擎**：提供「中英混合」、「僅英文」、「僅繁體中文」選項。若遇到純英文影片，單選英文模式能極大幅度降低 AI 把雜訊誤認成中文字的機率，並加快辨識速度。
- **🚀 高精度模式 (三重掃描策略)**：
  - 專為各種極端情形打造（如幾乎佔據整個螢幕的超鉅大空心字、或是藏在角落的超迷你說明文字）。
  - 在背景同時執行三道工序（基礎放大去找小字、輪廓閉運算、以及針對史詩級大字的**極限 0.3 倍縮小補洞技術**），確保 AI 絕不漏掉任何壯觀的開場標題！

### 安裝與執行

**方式一：使用打包好的 EXE（推薦）**
1. 點選此 GitHub 專案頁面右側的 **Releases** 區域。
2. 下載最新的執行檔 (exe) 。
3. 直接雙擊 `VideoTextExtractor.exe` 即可開啟圖形化介面運作，無需懂如何寫程式碼、也無需安裝任何 Python 環境！

**方式二：從原始碼執行**
1. 確保電腦已安裝 Python 3.8+。
2. 開啟終端機並安裝依賴套件：
   ```cmd
   pip install -r requirements.txt
   ```
3. 啟動 GUI 主程式：
   ```cmd
   python video_text_extractor_gui.py
   ```
*(註：建議您的系統環境有安裝 FFmpeg 全域變數，以利底層的 `yt-dlp` 能順利下載最高畫質影片素材供辨識)。*

### 輸出範例結構
```text
==================================================
  YouTube Video Text Extractor
  YouTube 影片文字擷取結果
==================================================

影片標題: Youtube Video Title
影片網址: https://www.youtube.com/watch?v=xxxxx
影片長度: 00:03:15

--------------------------------------------------

[00:00:01] Text
[00:00:05] Text
[00:00:10] Text
[00:00:15] Text

--------------------------------------------------
```
