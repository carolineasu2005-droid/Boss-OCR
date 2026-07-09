# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, copy_metadata


datas = []
binaries = []
hiddenimports = []

# Keep the GPL license and package metadata in the Windows one-dir release.
datas += copy_metadata("windmouse")

# Only the PyAutoGUI backend is used. Do not collect the optional AHK backend.
hiddenimports += [
    "windmouse.core",
    "windmouse.pyautogui_controller",
]

# RapidOCR ships ONNX models as package data. The remaining packages include
# dynamic backends/plugins that need explicit collection in a frozen build.
for package_name in (
    "rapidocr",
    "onnxruntime",
    "cv2",
    "PIL",
    "pyautogui",
    "pynput",
    "mss",
):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
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
    excludes=[],
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
    upx=True,
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
    upx=True,
    upx_exclude=[],
    name="BossOCR",
)
