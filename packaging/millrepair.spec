# -*- mode: python ; coding: utf-8 -*-
"""Сборка onedir. Один и тот же spec для Linux и Windows."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).resolve().parent
datas = collect_data_files("millrepair")
datas.append((str(root / "src" / "millrepair" / "data" / "default_model.json"), "millrepair/data"))
datas.append((str(root / "seed" / "default_model.json"), "seed"))

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("millrepair")
    + [
        "matplotlib.backends.backend_qtagg",
        "scipy.special",
        "scipy.optimize",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="millrepair",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(root / "packaging" / "icons" / "millrepair.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="millrepair",
)
