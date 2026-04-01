"""
PyInstaller 打包腳本 - GUI 版本
執行方式: python build_exe.py
"""
import subprocess
import sys
import os


def build():
    print("🔨 正在打包 VideoTextExtractor.exe (GUI 版)...")
    print("   這可能需要幾分鐘，請耐心等候...\n")

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--name', 'VideoTextExtractor',
        '--windowed',            # GUI 模式，不顯示命令列視窗
        '--console',             # 但保留 console 以方便除錯
        # 加入隱藏匯入
        '--hidden-import', 'easyocr',
        '--hidden-import', 'easyocr.model',
        '--hidden-import', 'easyocr.model.model',
        '--hidden-import', 'easyocr.utils',
        '--hidden-import', 'easyocr.craft_utils',
        '--hidden-import', 'easyocr.imgproc',
        '--hidden-import', 'easyocr.recognition',
        '--hidden-import', 'easyocr.detection',
        '--hidden-import', 'easyocr.detector',
        '--hidden-import', 'skimage',
        '--hidden-import', 'skimage.filters',
        '--hidden-import', 'skimage.transform',
        '--hidden-import', 'skimage.morphology',
        '--hidden-import', 'scipy',
        '--hidden-import', 'scipy.ndimage',
        '--hidden-import', 'PIL',
        '--hidden-import', 'yaml',
        # 收集 easyocr 整個套件（含模型設定檔）
        '--collect-all', 'easyocr',
        # 排除不需要的大型套件
        '--exclude-module', 'matplotlib',
        '--exclude-module', 'IPython',
        '--exclude-module', 'jupyter',
        '--exclude-module', 'notebook',
        # 主程式 - GUI 版
        'video_text_extractor_gui.py',
    ]

    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    if result.returncode == 0:
        exe_path = os.path.join('dist', 'VideoTextExtractor.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n✅ 打包完成！")
            print(f"📁 EXE 位置: {os.path.abspath(exe_path)}")
            print(f"📦 檔案大小: {size_mb:.1f} MB")
            print(f"\n使用方式: 直接雙擊 VideoTextExtractor.exe 即可開啟")
        else:
            print(f"\n⚠️ 打包似乎完成但找不到 EXE 檔案")
    else:
        print(f"\n❌ 打包失敗，錯誤碼: {result.returncode}")
        sys.exit(1)


if __name__ == '__main__':
    build()
