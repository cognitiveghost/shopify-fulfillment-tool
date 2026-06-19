# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# Collect full PySide6 runtime (Qt plugins, translations, etc.)
pyside6_datas, pyside6_binaries, pyside6_hidden = collect_all('PySide6')

# pymupdf ships as 'fitz' at import time
fitz_datas, fitz_binaries, fitz_hidden = collect_all('fitz')

a = Analysis(
    ['gui_main.py'],
    pathex=['.'],
    binaries=pyside6_binaries + fitz_binaries,
    datas=[
        ('data/templates', 'data/templates'),
        *pyside6_datas,
        *fitz_datas,
    ],
    hiddenimports=[
        # PostgreSQL
        'psycopg2',
        'psycopg2._psycopg',
        'psycopg2.extensions',
        'psycopg2.extras',
        # PDF / image
        'reportlab',
        'reportlab.graphics',
        'reportlab.pdfbase',
        'reportlab.pdfbase.ttfonts',
        'reportlab.platypus',
        'pypdf',
        'PIL',
        'PIL._imaging',
        'PIL.Image',
        # Barcode
        'barcode',
        'barcode.codex',
        'barcode.writer',
        # Excel
        'openpyxl',
        'xlrd',
        'xlwt',
        'xlutils',
        'xlsxwriter',
        # Data
        'pandas',
        'numpy',
        *pyside6_hidden,
        *fitz_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'IPython', 'notebook'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ShopifyFulfillmentTool',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ShopifyFulfillmentTool',
)
