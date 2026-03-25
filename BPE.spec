# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

datas = [('C:\\Users\\yklee\\Desktop\\CURSOR\\BPE_0325\\Cursor_save\\src\\setup_pro_common.py', '.'), ('C:\\Users\\yklee\\Desktop\\CURSOR\\BPE_0325\\Cursor_save\\src\\shotgrid_client.py', '.'), ('C:\\Users\\yklee\\Desktop\\CURSOR\\BPE_0325\\Cursor_save\\src\\nuke_setup_pro.py', '.'), ('C:\\Users\\yklee\\Desktop\\CURSOR\\BPE_0325\\Cursor_save\\src\\menu.py', '.'), ('C:\\Users\\yklee\\Desktop\\CURSOR\\BPE_0325\\Cursor_save\\src\\shot_node_template.nk', '.'), ('C:\\Users\\yklee\\Desktop\\CURSOR\\BPE_0325\\Cursor_save\\scripts\\install_to_nuke.bat', '.'), ('C:\\Users\\yklee\\Desktop\\CURSOR\\BPE_0325\\Cursor_save\\VERSION.txt', '.')]
binaries = []
hiddenimports = ['customtkinter', 'shotgun_api3', 'shotgun_api3.lib.httplib2', 'shotgun_api3.lib.sgtimezone', 'certifi', 'six', 'urllib3', 'tkinterdnd2']
datas += collect_data_files('customtkinter')
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\yklee\\Desktop\\CURSOR\\BPE_0325\\Cursor_save\\src\\setup_pro_manager.py'],
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
    a.binaries,
    a.datas,
    [],
    name='BPE_build_staging',
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
