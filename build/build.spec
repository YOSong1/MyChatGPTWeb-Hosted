# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec. 프로젝트 루트에서 실행: pyinstaller build/build.spec

환경변수
  MCW_ONEFILE=1  -> 단일 실행 파일. 기본은 폴더(onedir) 형태.
  MCW_VERSION    -> 산출물 이름에 붙일 버전 (선택)
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parent
ONEFILE = os.environ.get("MCW_ONEFILE", "0") == "1"
APP_NAME = "MyChatGPTWeb"

block_cipher = None

datas = [
    # Streamlit이 파일로 읽어 실행하는 2줄짜리 진입 스크립트. 앱 본체는 아래 hiddenimports로 PYZ에 들어간다.
    (str(ROOT / "streamlit_entry.py"), "."),
]
datas += copy_metadata("openai")

hiddenimports = (
    collect_submodules("app")  # 우리 코드: 평문이 아니라 바이트코드로 번들
    + collect_submodules("openai")
    + [
        "streamlit.runtime.scriptrunner.magic_funcs",
        "streamlit.web.bootstrap",
    ]
)

a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "build")],  # hook-streamlit.py
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 크기 절감. 사용하지 않는 무거운 패키지.
        "matplotlib", "scipy", "sklearn", "torch", "IPython", "notebook", "pytest",
        "tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
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
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=APP_NAME,
    )
    if sys.platform == "darwin":
        app = BUNDLE(
            coll,
            name=f"{APP_NAME}.app",
            icon=None,
            bundle_identifier="local.mychatgptweb",
            info_plist={
                "CFBundleShortVersionString": os.environ.get("MCW_VERSION", "1.0.0"),
                "NSHighResolutionCapable": True,
            },
        )
