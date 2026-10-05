# -*- mode: python ; coding: utf-8 -*-
# Build with:  pyinstaller build.spec
# Output:      dist/YouTube Downloader PRO(.exe)

from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("customtkinter")
datas += [("assets", "assets")]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="YouTube Downloader PRO",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon="assets/icon.ico",
)
