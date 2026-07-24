# -*- mode: python ; coding: utf-8 -*-
from glob import glob


a = Analysis(
    ['src/main.py'],
    pathex=['src', '.'],  # Added '.' for project root (to find 'shared' module)
    binaries=[],
    datas=[
        *[(qss, 'src') for qss in glob('src/*.qss')],
        ('config.ini.example', '.'),
        ('shared', 'shared'),  # Include shared module directory
    ],
    hiddenimports=[
        'exceptions',
        'session_lock_manager',
        'restore_session_dialog',
        'logger',
        'profile_manager',
        'session_manager',
        'shared',
        'shared.stats_manager',
    ],
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
    name='Packers-Assistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
