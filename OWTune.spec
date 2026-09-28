# -*- mode: python ; coding: utf-8 -*-
# 빌드: .venv\Scripts\pyinstaller OWTune.spec  →  dist\OWTune.exe
a = Analysis(
    ["run_owtune.py"],
    datas=[("owtune/data", "owtune/data")],
    hiddenimports=["win32com.shell.shell", "win32com.shell.shellcon"],
    excludes=["tkinter", "unittest", "pytest", "PIL", "numpy"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="OWTune",
    icon="owtune/data/icon.ico",
    console=False,
    upx=False,
)
