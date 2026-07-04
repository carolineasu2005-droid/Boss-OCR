# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all


datas = []
binaries = []
hiddenimports = [
    "tkinter",
    "tkinter.constants",
    "tkinter.filedialog",
    "pynput.keyboard._darwin",
    "pynput.mouse._darwin",
]

# RapidOCR includes ONNX model data, while several runtime dependencies load
# platform backends or plugins dynamically. Keep this list macOS-specific so
# the existing Windows packaging spec and workflow remain untouched.
for package_name in (
    "rapidocr",
    "onnxruntime",
    "cv2",
    "PIL",
    "numpy",
    "pyautogui",
    "pynput",
    "mss",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(
        package_name
    )
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports


a = Analysis(
    ["simple_brush.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "win32clipboard",
        "win32con",
        "win32gui",
        "win32process",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BossOCR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BossOCR",
)

