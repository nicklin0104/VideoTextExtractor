#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Video Text Extractor (GUI Version)
============================================
從 YouTube 影片中擷取畫面上出現的所有文字，並記錄出現時間。
提供圖形化介面，支援最多 5 個 YouTube 連結同時排隊處理。
"""

import os
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from collections import OrderedDict
from datetime import datetime
from difflib import SequenceMatcher

import cv2
import easyocr
import yt_dlp


# ─── 核心處理函式 ─────────────────────────────────────────

def format_timestamp(seconds):
    """將秒數轉換為 HH:MM:SS 格式"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def sanitize_filename(name):
    """移除檔名中的非法字元"""
    illegal_chars = r'<>:"/\|?*'
    for ch in illegal_chars:
        name = name.replace(ch, '_')
    name = name.rstrip('. ')
    if len(name) > 100:
        name = name[:100]
    return name


def download_video(url, output_dir, progress_callback=None):
    """下載 YouTube 影片"""
    video_info = {}

    def progress_hook(d):
        if d['status'] == 'downloading' and progress_callback:
            if 'total_bytes' in d and d['total_bytes']:
                pct = d['downloaded_bytes'] / d['total_bytes'] * 100
                progress_callback(f"下載中... {pct:.0f}%")
            elif '_percent_str' in d:
                progress_callback(f"下載中... {d['_percent_str'].strip()}")
        elif d['status'] == 'finished' and progress_callback:
            progress_callback("下載完成，正在處理...")

    ydl_opts = {
        'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best',
        'merge_output_format': 'mp4',
        'outtmpl': os.path.join(output_dir, '%(id)s.%(ext)s'),
        'progress_hooks': [progress_hook],
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        video_info['title'] = info.get('title', 'Unknown')
        video_info['duration'] = info.get('duration', 0)
        video_info['id'] = info.get('id', 'unknown')

        if progress_callback:
            progress_callback(f"正在下載: {video_info['title']}")

        ydl.download([url])

        video_path = os.path.join(output_dir, f"{video_info['id']}.mp4")
        if not os.path.exists(video_path):
            for ext in ['mp4', 'mkv', 'webm']:
                candidate = os.path.join(output_dir, f"{video_info['id']}.{ext}")
                if os.path.exists(candidate):
                    video_path = candidate
                    break

        if not os.path.exists(video_path):
            raise FileNotFoundError("找不到下載的影片檔案")

        return video_path, video_info


def extract_frames(video_path, interval=1.0, progress_callback=None, stop_event=None):
    """從影片中按照固定間隔擷取影格"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"無法開啟影片: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    frame_interval = int(fps * interval)
    if frame_interval < 1:
        frame_interval = 1

    total_captures = int(duration / interval) + 1
    frames = []
    frame_idx = 0
    captured = 0

    while True:
        if stop_event and stop_event.is_set():
            break
            
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            timestamp = frame_idx / fps
            frames.append((timestamp, frame))
            captured += 1
            if progress_callback:
                progress_callback(f"擷取影格中... {captured}/{total_captures}")
        frame_idx += 1

    cap.release()
    return frames


def group_texts_into_lines(ocr_result, confidence_threshold=0.3):
    """
    將 ocr_result 中的文字依據 Y 座標分列，並在各列中依據 X 座標排序。
    這可確保同一橫列的文字接在同一行，若多列則以多行輸出。
    """
    if not ocr_result:
        return []

    def calculate_ioa(box1, box2):
        x_min1, x_max1 = min(p[0] for p in box1), max(p[0] for p in box1)
        y_min1, y_max1 = min(p[1] for p in box1), max(p[1] for p in box1)
        x_min2, x_max2 = min(p[0] for p in box2), max(p[0] for p in box2)
        y_min2, y_max2 = min(p[1] for p in box2), max(p[1] for p in box2)

        inter_x_min = max(x_min1, x_min2)
        inter_y_min = max(y_min1, y_min2)
        inter_x_max = min(x_max1, x_max2)
        inter_y_max = min(y_max1, y_max2)

        if inter_x_max <= inter_x_min or inter_y_max <= inter_y_min:
            return 0.0

        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        area1 = (x_max1 - x_min1) * (y_max1 - y_min1)
        area2 = (x_max2 - x_min2) * (y_max2 - y_min2)

        return inter_area / min(area1, area2)

    filtered = []
    # 根據文字長度預先排序，優先保留長字串
    sorted_res = sorted([res for res in ocr_result if res[2] >= confidence_threshold and res[1].strip()], 
                        key=lambda x: (len(x[1].strip()), x[2]), reverse=True)
    
    for item in sorted_res:
        box, text, conf = item
        is_dup = False
        for f_item in filtered:
            f_box, f_text, f_conf = f_item
            if calculate_ioa(box, f_box) > 0.6:  # 重疊超過 60% 視為相同
                is_dup = True
                break
        if not is_dup:
            filtered.append(item)

    items = []
    for bbox, text, conf in filtered:
        cl_text = text.strip()
        y_min = min(p[1] for p in bbox)
        y_max = max(p[1] for p in bbox)
        x_min = min(p[0] for p in bbox)
        x_max = max(p[0] for p in bbox)
        cy = (y_min + y_max) / 2
        h = y_max - y_min
        items.append({
            'text': cl_text, 'cy': cy, 'y_min': y_min, 'y_max': y_max, 
            'x_min': x_min, 'x_max': x_max, 'h': h
        })

    # 對 Y 軸 (中心) 排序
    items.sort(key=lambda x: x['cy'])

    lines = []
    current_line = []

    for item in items:
        if not current_line:
            current_line.append(item)
            continue

        ref = current_line[-1]
        avg_cy = sum(x['cy'] for x in current_line) / len(current_line)
        avg_h = sum(x['h'] for x in current_line) / len(current_line)
        
        cy_diff = abs(item['cy'] - avg_cy)
        overlap = max(0, min(item['y_max'], ref['y_max']) - max(item['y_min'], ref['y_min']))
        min_h = min(item['h'], ref['h'])
        
        if cy_diff < avg_h * 0.4 or overlap > min_h * 0.5:
            current_line.append(item)
        else:
            lines.append(current_line)
            current_line = [item]
            
    if current_line:
        lines.append(current_line)

    result_lines = []
    for line in lines:
        line.sort(key=lambda x: x['x_min'])
        seen = []
        line_parts = []
        for item in line:
            txt_lower = item['text'].lower()
            is_dup_substr = False
            for s in seen:
                if txt_lower in s or s in txt_lower:
                    is_dup_substr = True
                    break
            if not is_dup_substr:
                line_parts.append(item['text'])
                seen.append(txt_lower)
        if line_parts:
            result_lines.append(" ".join(line_parts))

    return result_lines


def ocr_frames(frames, reader, confidence_threshold=0.3, progress_callback=None, high_accuracy=False, stop_event=None):
    """對每個影格執行 OCR 辨識"""
    results = []
    total = len(frames)

    for i, (timestamp, frame) in enumerate(frames):
        if stop_event and stop_event.is_set():
            break

        if high_accuracy:
            # 優化: OpenCV 預處理 (轉換為灰階)
            processed_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # 優化: 圖形學閉運算 (Morphological Close) 使用小 kernel 來特別填補「超大外框字」的空隙，但保留原圖給小字
            import numpy as np
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            processed_frame_closed = cv2.morphologyEx(processed_frame, cv2.MORPH_CLOSE, kernel)
            
            # 三重掃描策略 (涵蓋極小到超巨大字體)
            # Pass 1: mag_ratio=1.5 放大影像，抓小字與一般字，使用未經閉運算的灰階影像以避免小字糊掉
            res1 = reader.readtext(processed_frame, mag_ratio=1.5, adjust_contrast=0.5)
            # Pass 2: mag_ratio=0.7 縮小影像，抓大字
            res2 = reader.readtext(processed_frame_closed, mag_ratio=0.7, text_threshold=0.4, link_threshold=0.2)
            # Pass 3: mag_ratio=0.3 極限縮小影像，特別抓佔據整個螢幕的「超大滿版字」(例如 IT'S TAKEN)
            res3 = reader.readtext(processed_frame_closed, mag_ratio=0.3, text_threshold=0.3, link_threshold=0.2)
            
            ocr_result = res1 + res2 + res3
        else:
            ocr_result = reader.readtext(frame)
            
        formatted_lines = group_texts_into_lines(ocr_result, confidence_threshold)
                    
        if formatted_lines:
            results.append((timestamp, formatted_lines))
        if progress_callback:
            progress_callback(f"辨識文字中... {i + 1}/{total}")

    return results


def merge_same_timestamp_texts(results):
    """
    將同一秒出現的所有文字合併成一行。
    先將 timestamp 取整數（秒），然後把同一秒的文字用空格串接。
    """
    merged = OrderedDict()
    for timestamp, lines in results:
        sec = int(timestamp)
        if sec not in merged:
            merged[sec] = lines
        else:
            # 只在秒數內的第一次出現結果紀錄，或者採用行數最多的
            # 這裡簡單處理：若同一秒有多個 frame，選取出文字行數或者文字總長度較多者，
            # 以避免重複接上相同的句子。
            current_len = sum(len(l) for l in merged[sec])
            new_len = sum(len(l) for l in lines)
            if new_len > current_len:
                merged[sec] = lines
    return list(merged.items())


def deduplicate_results(merged_results, similarity_threshold=0.8):
    """
    智慧去重：移除連續時間點中重複出現的相同文字。
    輸入是 merge_same_timestamp_texts 的結果: [(sec, [lines]), ...]
    """
    if not merged_results:
        return merged_results

    deduplicated = []
    prev_combined = ""

    for sec, lines in merged_results:
        # 將該時間點的所有行列用換行符串成一個區塊比對
        combined = "\n".join(lines)

        # 比較整行合併後的文字與前一秒是否高度相似
        if prev_combined:
            similarity = SequenceMatcher(None, combined, prev_combined).ratio()
            if similarity >= similarity_threshold:
                prev_combined = combined
                continue

        deduplicated.append((sec, lines))
        prev_combined = combined

    return deduplicated


def save_results(results, video_info, url, interval, output_path):
    """將結果儲存為格式化的文字檔"""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("=" * 50 + "\n")
        f.write("  YouTube Video Text Extractor\n")
        f.write("  YouTube 影片文字擷取結果\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"影片標題: {video_info.get('title', 'Unknown')}\n")
        f.write(f"影片網址: {url}\n")
        f.write(f"影片長度: {format_timestamp(video_info.get('duration', 0))}\n")
        f.write(f"擷取間隔: {interval} 秒\n")
        f.write(f"處理時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"辨識語言: 繁體中文, 英文\n")
        f.write("\n" + "-" * 50 + "\n\n")

        if not results:
            f.write("（未偵測到任何文字）\n")
        else:
            for sec, lines in results:
                time_str = format_timestamp(sec)
                # 每個元素都是已經經過 Y 軸分列與 X 軸排序的單行文字
                for line in lines:
                    f.write(f"[{time_str}] {line}\n")

            total_entries = len(results)
            f.write(f"\n" + "-" * 50 + "\n")
            f.write(f"共偵測到 {total_entries} 個時間點的文字\n")

    return output_path


# ─── GUI 應用程式 ─────────────────────────────────────────

class VideoTextExtractorApp:
    # 色彩配置
    BG_DARK = "#1a1a2e"
    BG_CARD = "#16213e"
    BG_INPUT = "#0f3460"
    ACCENT = "#e94560"
    ACCENT_HOVER = "#ff6b81"
    TEXT_PRIMARY = "#ffffff"
    TEXT_SECONDARY = "#a8b2d1"
    TEXT_DIM = "#6272a4"
    SUCCESS = "#50fa7b"
    WARNING = "#ffb86c" # 改為較亮的橘色，避免在深色背景看不清
    ERROR = "#ff5555"
    BORDER = "#2a2a4a"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("YouTube Video Text Extractor")
        self.root.geometry("780x820")
        self.root.minsize(700, 750)
        self.root.configure(bg=self.BG_DARK)
        self.root.resizable(True, True)

        # 設定 icon（如果可用）
        try:
            self.root.iconbitmap(default='')
        except Exception:
            pass

        # 狀態變數
        self.is_processing = False
        self.ocr_reader = None
        self.current_ocr_langs = None
        self.output_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        self.url_entries = []
        self.status_labels = []
        self.interval_var = tk.DoubleVar(value=1.0)
        self.confidence_var = tk.DoubleVar(value=0.3)
        self.high_accuracy_var = tk.BooleanVar(value=False)
        self.language_var = tk.StringVar(value="繁體中文 + 英文")

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        """建構使用者介面"""
        # 主框架
        main_frame = tk.Frame(self.root, bg=self.BG_DARK)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        # ── 標題區 ──
        title_frame = tk.Frame(main_frame, bg=self.BG_DARK)
        title_frame.pack(fill=tk.X, pady=(0, 15))

        tk.Label(
            title_frame,
            text="🎬 YouTube 影片文字擷取工具",
            font=("Microsoft JhengHei UI", 18, "bold"),
            fg=self.TEXT_PRIMARY, bg=self.BG_DARK
        ).pack(side=tk.LEFT)

        tk.Label(
            title_frame,
            text="Video Text Extractor",
            font=("Segoe UI", 10),
            fg=self.TEXT_DIM, bg=self.BG_DARK
        ).pack(side=tk.LEFT, padx=(10, 0), pady=(8, 0))

        # ── URL 輸入區 ──
        url_card = tk.Frame(main_frame, bg=self.BG_CARD, highlightbackground=self.BORDER, highlightthickness=1)
        url_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            url_card,
            text="📋 YouTube 連結（最多 5 個）",
            font=("Microsoft JhengHei UI", 11, "bold"),
            fg=self.TEXT_PRIMARY, bg=self.BG_CARD
        ).pack(anchor=tk.W, padx=15, pady=(12, 8))

        for i in range(5):
            row = tk.Frame(url_card, bg=self.BG_CARD)
            row.pack(fill=tk.X, padx=15, pady=3)

            tk.Label(
                row,
                text=f"#{i + 1}",
                font=("Segoe UI", 10, "bold"),
                fg=self.ACCENT, bg=self.BG_CARD,
                width=3
            ).pack(side=tk.LEFT)

            entry = tk.Entry(
                row,
                font=("Segoe UI", 10),
                bg=self.BG_INPUT, fg=self.TEXT_PRIMARY,
                insertbackground=self.TEXT_PRIMARY,
                relief=tk.FLAT,
                highlightbackground=self.BORDER,
                highlightthickness=1,
                highlightcolor=self.ACCENT,
            )
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 10), ipady=4)
            self.url_entries.append(entry)

            status_lbl = tk.Label(
                row,
                text="",
                font=("Segoe UI", 9),
                fg=self.TEXT_DIM, bg=self.BG_CARD,
                width=12, anchor=tk.W
            )
            status_lbl.pack(side=tk.RIGHT)
            self.status_labels.append(status_lbl)

        # URL 區底部間距
        tk.Frame(url_card, bg=self.BG_CARD, height=10).pack()

        # ── 設定區 ──
        settings_card = tk.Frame(main_frame, bg=self.BG_CARD, highlightbackground=self.BORDER, highlightthickness=1)
        settings_card.pack(fill=tk.X, pady=(0, 10))

        tk.Label(
            settings_card,
            text="⚙️  設定",
            font=("Microsoft JhengHei UI", 11, "bold"),
            fg=self.TEXT_PRIMARY, bg=self.BG_CARD
        ).pack(anchor=tk.W, padx=15, pady=(12, 8))

        settings_inner = tk.Frame(settings_card, bg=self.BG_CARD)
        settings_inner.pack(fill=tk.X, padx=15, pady=(0, 12))

        # 辨識語言
        tk.Label(
            settings_inner,
            text="辨識語言:",
            font=("Microsoft JhengHei UI", 10),
            fg=self.TEXT_SECONDARY, bg=self.BG_CARD
        ).grid(row=0, column=0, sticky=tk.W, pady=4)

        lang_combo = ttk.Combobox(
            settings_inner,
            textvariable=self.language_var,
            values=["繁體中文 + 英文", "僅英文", "僅繁體中文"],
            state="readonly",
            width=14,
            font=("Segoe UI", 10)
        )
        lang_combo.grid(row=0, column=1, padx=(10, 20), pady=4)

        # 擷取間隔
        tk.Label(
            settings_inner,
            text="間隔（秒）:",
            font=("Microsoft JhengHei UI", 10),
            fg=self.TEXT_SECONDARY, bg=self.BG_CARD
        ).grid(row=0, column=2, sticky=tk.W, pady=4)

        interval_spin = tk.Spinbox(
            settings_inner,
            from_=0.5, to=5.0, increment=0.5,
            textvariable=self.interval_var,
            width=5,
            font=("Segoe UI", 10),
            bg=self.BG_INPUT, fg=self.TEXT_PRIMARY,
            buttonbackground=self.BG_INPUT,
            relief=tk.FLAT,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        interval_spin.grid(row=0, column=3, padx=(10, 20), pady=4)

        # 信心度門檻
        tk.Label(
            settings_inner,
            text="信心度:",
            font=("Microsoft JhengHei UI", 10),
            fg=self.TEXT_SECONDARY, bg=self.BG_CARD
        ).grid(row=0, column=4, sticky=tk.W, pady=4)

        confidence_spin = tk.Spinbox(
            settings_inner,
            from_=0.1, to=0.9, increment=0.1,
            textvariable=self.confidence_var,
            width=5,
            font=("Segoe UI", 10),
            bg=self.BG_INPUT, fg=self.TEXT_PRIMARY,
            buttonbackground=self.BG_INPUT,
            relief=tk.FLAT,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        confidence_spin.grid(row=0, column=5, padx=(10, 20), pady=4)

        # 高精度模式
        high_acc_cb = tk.Checkbutton(
            settings_inner,
            text="🚀 高精度",
            font=("Microsoft JhengHei UI", 10),
            fg=self.TEXT_PRIMARY, bg=self.BG_CARD,
            activebackground=self.BG_CARD, activeforeground=self.TEXT_PRIMARY,
            selectcolor=self.BG_INPUT,
            variable=self.high_accuracy_var
        )
        high_acc_cb.grid(row=0, column=6, padx=(0, 0), pady=4)

        # 輸出目錄
        output_row = tk.Frame(settings_card, bg=self.BG_CARD)
        output_row.pack(fill=tk.X, padx=15, pady=(0, 12))

        tk.Label(
            output_row,
            text="輸出目錄:",
            font=("Microsoft JhengHei UI", 10),
            fg=self.TEXT_SECONDARY, bg=self.BG_CARD
        ).pack(side=tk.LEFT)

        self.output_dir_var = tk.StringVar(value=self.output_dir)
        self.output_dir_entry = tk.Entry(
            output_row,
            textvariable=self.output_dir_var,
            font=("Segoe UI", 9),
            bg=self.BG_INPUT, fg=self.TEXT_PRIMARY,
            insertbackground=self.TEXT_PRIMARY,
            relief=tk.FLAT,
            highlightbackground=self.BORDER,
            highlightthickness=1,
        )
        self.output_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 5), ipady=3)

        browse_btn = tk.Button(
            output_row,
            text="瀏覽",
            font=("Microsoft JhengHei UI", 9),
            bg=self.BG_INPUT, fg=self.TEXT_SECONDARY,
            activebackground=self.ACCENT,
            activeforeground=self.TEXT_PRIMARY,
            relief=tk.FLAT, cursor="hand2",
            command=self._browse_output_dir,
            padx=10
        )
        browse_btn.pack(side=tk.RIGHT)

        # ── 按鈕區 ──
        btn_frame = tk.Frame(main_frame, bg=self.BG_DARK)
        btn_frame.pack(fill=tk.X, pady=(5, 10))

        # 定義停止事件
        self.stop_event = threading.Event()

        self.start_btn = tk.Button(
            btn_frame,
            text="▶  開始擷取文字",
            font=("Microsoft JhengHei UI", 13, "bold"),
            bg=self.ACCENT, fg=self.TEXT_PRIMARY,
            activebackground=self.ACCENT_HOVER,
            activeforeground=self.TEXT_PRIMARY,
            relief=tk.FLAT,
            cursor="hand2",
            command=self._start_processing,
            padx=30, pady=8
        )
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.stop_btn = tk.Button(
            btn_frame,
            text="⏹ 停止",
            font=("Microsoft JhengHei UI", 13, "bold"),
            bg=self.BORDER, fg=self.TEXT_PRIMARY,
            activebackground=self.ERROR,
            activeforeground=self.TEXT_PRIMARY,
            relief=tk.FLAT,
            cursor="hand2",
            state=tk.DISABLED,
            command=self._stop_processing,
            padx=20, pady=8
        )
        self.stop_btn.pack(side=tk.RIGHT)

        # ── 進度與日誌區 ──
        log_card = tk.Frame(main_frame, bg=self.BG_CARD, highlightbackground=self.BORDER, highlightthickness=1)
        log_card.pack(fill=tk.BOTH, expand=True, pady=(0, 0))

        log_header = tk.Frame(log_card, bg=self.BG_CARD)
        log_header.pack(fill=tk.X, padx=15, pady=(12, 5))

        tk.Label(
            log_header,
            text="📊 處理進度",
            font=("Microsoft JhengHei UI", 11, "bold"),
            fg=self.TEXT_PRIMARY, bg=self.BG_CARD
        ).pack(side=tk.LEFT)

        self.overall_status = tk.Label(
            log_header,
            text="等待開始...",
            font=("Segoe UI", 9),
            fg=self.TEXT_DIM, bg=self.BG_CARD
        )
        self.overall_status.pack(side=tk.RIGHT)

        # 進度條
        style = ttk.Style()
        style.theme_use('default')
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor=self.BG_INPUT,
            background=self.ACCENT,
            thickness=8
        )

        self.progress_bar = ttk.Progressbar(
            log_card,
            style="Custom.Horizontal.TProgressbar",
            orient=tk.HORIZONTAL,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X, padx=15, pady=(0, 8))

        # 日誌文字區
        self.log_text = tk.Text(
            log_card,
            font=("Consolas", 9),
            bg=self.BG_DARK, fg=self.TEXT_SECONDARY,
            relief=tk.FLAT,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=10,
            insertbackground=self.TEXT_PRIMARY,
            selectbackground=self.ACCENT,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 12))

        # 設定日誌標籤顏色
        self.log_text.tag_configure("info", foreground=self.TEXT_SECONDARY)
        self.log_text.tag_configure("success", foreground=self.SUCCESS)
        self.log_text.tag_configure("warning", foreground=self.WARNING)
        self.log_text.tag_configure("error", foreground=self.ERROR)
        self.log_text.tag_configure("accent", foreground=self.ACCENT)

    def _browse_output_dir(self):
        """選擇輸出目錄"""
        directory = filedialog.askdirectory(
            title="選擇輸出目錄",
            initialdir=self.output_dir_var.get()
        )
        if directory:
            self.output_dir_var.set(directory)

    def _log(self, message, tag="info"):
        """寫入日誌"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _set_url_status(self, index, text, color=None):
        """設定某個 URL 的狀態文字"""
        if color is None:
            color = self.TEXT_DIM
        self.status_labels[index].config(text=text, fg=color)

    def _start_processing(self):
        """開始處理"""
        if self.is_processing:
            return

        # 收集有效的 URL
        urls = []
        for i, entry in enumerate(self.url_entries):
            url = entry.get().strip()
            if url:
                urls.append((i, url))
            self._set_url_status(i, "")

        if not urls:
            messagebox.showwarning("提醒", "請至少輸入一個 YouTube 連結！")
            return

        # 驗證輸出目錄
        output_dir = self.output_dir_var.get().strip()
        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showwarning("提醒", "請選擇有效的輸出目錄！")
            return

        self.is_processing = True
        self.stop_event.clear()
        self.start_btn.config(state=tk.DISABLED, bg=self.TEXT_DIM)
        self.stop_btn.config(state=tk.NORMAL, bg=self.ACCENT)

        # 清空日誌
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

        # 在背景執行緒中處理
        thread = threading.Thread(
            target=self._process_videos,
            args=(urls, output_dir),
            daemon=True
        )
        thread.start()

    def _process_videos(self, urls, output_dir):
        """在背景執行緒中處理所有影片"""
        total = len(urls)
        interval = self.interval_var.get()
        confidence = self.confidence_var.get()
        high_acc = self.high_accuracy_var.get()
        lang_choice = self.language_var.get()

        self.root.after(0, lambda: self._log(f"共 {total} 個影片待處理", "accent"))
        self.root.after(0, lambda: self._log(f"間隔: {interval}s | 信心: {confidence} | 高精度: {'是' if high_acc else '否'} | 語言: {lang_choice}", "info"))

        # 解析選擇的語言
        if lang_choice == "僅英文":
            target_langs = ['en']
        elif lang_choice == "僅繁體中文":
            target_langs = ['ch_tra']
        else:
            target_langs = ['ch_tra', 'en']

        # 初始化 OCR（若尚未初始化或語言已變更）
        if self.ocr_reader is None or self.current_ocr_langs != target_langs:
            self.root.after(0, lambda: self._update_status("正在載入 OCR 引擎..."))
            self.root.after(0, lambda: self._log(f"初始化 OCR 引擎 (語言: {target_langs})，首次需稍候...", "warning"))
            try:
                self.ocr_reader = easyocr.Reader(target_langs, gpu=False, verbose=False)
                self.current_ocr_langs = target_langs
                self.root.after(0, lambda: self._log("OCR 引擎就緒！", "success"))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"OCR 引擎初始化失敗: {e}", "error"))
                self.root.after(0, self._finish_processing)
                return

        success_count = 0

        for idx, (url_index, url) in enumerate(urls):
            self.root.after(0, lambda i=idx, t=total: self.progress_bar.config(value=(i / t) * 100))
            self.root.after(0, lambda i=url_index: self._set_url_status(i, "⏳ 處理中...", self.WARNING))
            self.root.after(0, lambda u=url, i=idx: self._log(f"\n{'─' * 40}", "info"))
            self.root.after(0, lambda u=url, i=idx, t=total: self._log(f"處理第 {i + 1}/{t} 個影片: {u}", "accent"))

            try:
                result_path = self._process_single_video(url, url_index, output_dir, interval, confidence, high_acc)
                if self.stop_event.is_set():
                    break
                
                success_count += 1
                self.root.after(0, lambda i=url_index: self._set_url_status(i, "✅ 完成", self.SUCCESS))
                self.root.after(0, lambda p=result_path: self._log(f"已儲存: {os.path.basename(p)}", "success"))
            except Exception as e:
                if self.stop_event.is_set():
                    self.root.after(0, lambda i=url_index: self._set_url_status(i, "⏹ 已停止", self.TEXT_DIM))
                    break
                self.root.after(0, lambda i=url_index: self._set_url_status(i, "❌ 失敗", self.ERROR))
                self.root.after(0, lambda err=str(e): self._log(f"錯誤: {err}", "error"))

        # 完成
        if self.stop_event.is_set():
            self.root.after(0, lambda: self._log(f"\n⚠️ 處理已被使用者中斷！", "warning"))
        else:
            self.root.after(0, lambda: self.progress_bar.config(value=100))
        
        self.root.after(0, lambda: self._log(f"\n{'═' * 40}", "info"))
        self.root.after(0, lambda s=success_count, t=total: self._log(
            f"全部完成！成功 {s}/{t} 個影片", "success"
        ))
        self.root.after(0, lambda d=output_dir: self._log(f"輸出目錄: {d}", "info"))
        self.root.after(0, self._finish_processing)

    def _process_single_video(self, url, url_index, output_dir, interval, confidence, high_acc):
        """處理單一影片"""
        temp_dir = tempfile.mkdtemp(prefix='vte_')

        try:
            # Step 1: 下載影片
            def dl_progress(msg):
                self.root.after(0, lambda m=msg: self._update_status(m))

            video_path, video_info = download_video(url, temp_dir, progress_callback=dl_progress)
            self.root.after(0, lambda t=video_info['title']: self._log(f"影片: {t} ({format_timestamp(video_info['duration'])})", "info"))

            # Step 2: 擷取影格
            def frame_progress(msg):
                self.root.after(0, lambda m=msg: self._update_status(m))

            frames = extract_frames(video_path, interval, progress_callback=frame_progress, stop_event=self.stop_event)
            self.root.after(0, lambda n=len(frames): self._log(f"擷取了 {n} 個影格", "info"))

            if self.stop_event.is_set():
                raise InterruptedError("使用者停止")

            # Step 3: OCR 辨識
            def ocr_progress(msg):
                self.root.after(0, lambda m=msg: self._update_status(m))

            results = ocr_frames(frames, self.ocr_reader, confidence, progress_callback=ocr_progress, high_accuracy=high_acc, stop_event=self.stop_event)

            if self.stop_event.is_set():
                raise InterruptedError("使用者停止")

            # Step 4: 合併同一秒的文字
            merged = merge_same_timestamp_texts(results)

            # Step 5: 去重
            deduplicated = deduplicate_results(merged)
            self.root.after(0, lambda o=len(merged), d=len(deduplicated): self._log(
                f"文字時間點: {o} → 去重後: {d}", "info"
            ))

            # Step 6: 儲存
            safe_title = sanitize_filename(video_info.get('title', 'video'))
            output_path = os.path.join(output_dir, f"{safe_title}_text_extract.txt")

            # 避免檔名重複
            if os.path.exists(output_path):
                base, ext = os.path.splitext(output_path)
                counter = 1
                while os.path.exists(f"{base}_{counter}{ext}"):
                    counter += 1
                output_path = f"{base}_{counter}{ext}"

            save_results(deduplicated, video_info, url, interval, output_path)
            return output_path

        finally:
            # 清理暫存檔案
            try:
                for f in os.listdir(temp_dir):
                    os.remove(os.path.join(temp_dir, f))
                os.rmdir(temp_dir)
            except Exception:
                pass

    def _update_status(self, text):
        """更新整體狀態文字"""
        self.overall_status.config(text=text)

    def _stop_processing(self):
        """使用者請求停止"""
        if self.is_processing:
            if messagebox.askyesno("停止確認", "確定要停止後續的文字擷取嗎？\n（目前正在處理的影片可能需要等一小段時間才會完全停止）"):
                self.stop_event.set()
                self._update_status("正在停止中...")
                self.stop_btn.config(state=tk.DISABLED)

    def _finish_processing(self):
        """處理完成後的清理"""
        self.is_processing = False
        self.start_btn.config(state=tk.NORMAL, bg=self.ACCENT)
        self.stop_btn.config(state=tk.DISABLED, bg=self.BORDER)
        status_text = "處理完成！" if not self.stop_event.is_set() else "已停止"
        self._update_status(status_text)

    def _on_close(self):
        """關閉視窗"""
        if self.is_processing:
            if not messagebox.askyesno("確認", "正在處理中，確定要強制關閉嗎？"):
                return
            self.stop_event.set()
        self.root.destroy()

    def run(self):
        """啟動應用程式"""
        self.root.mainloop()


if __name__ == '__main__':
    app = VideoTextExtractorApp()
    app.run()
