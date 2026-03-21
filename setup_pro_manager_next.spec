# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = [('C:\\Users\\YoungKyu\\Desktop\\Cursor_save\\src\\setup_pro_common.py', '.'), ('C:\\Users\\YoungKyu\\Desktop\\Cursor_save\\src\\nuke_setup_pro.py', '.'), ('C:\\Users\\YoungKyu\\Desktop\\Cursor_save\\src\\menu.py', '.'), ('C:\\Users\\YoungKyu\\Desktop\\Cursor_save\\src\\shot_node_template.nk', '.'), ('C:\\Users\\YoungKyu\\Desktop\\Cursor_save\\scripts\\install_to_nuke.bat', '.'), ('C:\\Users\\YoungKyu\\Desktop\\Cursor_save\\VERSION.txt', '.')]
datas += collect_data_files('customtkinter')


a = Analysis(
    ['C:\\Users\\YoungKyu\\Desktop\\Cursor_save\\src\\setup_pro_manager.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['customtkinter'],
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
    a.binaries,
    a.datas,
    [],
    name='setup_pro_manager_next',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
