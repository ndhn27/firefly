# -*- mode: python ; coding: utf-8 -*-
# Đóng gói thành thư mục chạy được không cần cài Python:
#   python -m PyInstaller firefly.spec --noconfirm --clean      (hoặc bấm build_exe.bat trên Windows)
# Kết quả: dist/FireflyVideo/FireflyVideo(.exe). Dự án, nhật ký, ai_settings.json được ghi cạnh file .exe (xem paths.py).
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

HERE = os.path.abspath(SPECPATH)

datas = [(os.path.join(HERE, "static"), "static"), (os.path.join(HERE, "fonts"), "fonts"), (os.path.join(HERE, "LICENSE"), ".")]
datas += collect_data_files("imageio_ffmpeg")  # kèm sẵn file ffmpeg để máy không cần cài
datas += collect_data_files("certifi")         # chứng chỉ SSL cho edge-tts (giọng đọc)
hidden = collect_submodules("edge_tts") + collect_submodules("pydantic") + ["pydantic_core"]
try:  # gTTS (giọng dự phòng, tuỳ chọn) được import lười trong tts.py nên PyInstaller không tự thấy; chỉ kèm theo nếu máy build đã cài
    import gtts  # noqa: F401
    hidden += collect_submodules("gtts")
    datas += collect_data_files("gtts")
except ImportError:
    pass

a = Analysis(
    ["app.py"],
    pathex=[HERE],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "playwright", "matplotlib", "IPython", "notebook", "scipy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FireflyVideo", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="FireflyVideo", upx=False)
