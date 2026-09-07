# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = ['anyio', 'starlette.routing']

# Datenfiles der Pakete einsammeln
datas += collect_data_files('gradio')
datas += collect_data_files('gradio_client')
datas += collect_data_files('safehttpx')

# numpy komplett (Tuple: (datas, binaries, hiddenimports))
d, b, h = collect_all('numpy')
datas += d; binaries += b; hiddenimports += h

# groovy komplett – wichtig wegen version.txt & Co.
d, b, h = collect_all('groovy')
datas += d; binaries += b; hiddenimports += h

# Gradio-Submodule sicherheitshalber explizit
hiddenimports += collect_submodules('gradio')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_no_pyi.py'],   # Runtime-Hook aktivieren
    excludes=[],
    noarchive=False,
    optimize=0,
    # WICHTIG: Gradio/Groovy als .py sammeln (nicht nur .pyc in der Zipsammlung)
    module_collection_mode={
        "gradio": "py",
        "groovy": "py",
    },
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='mcp_email_server_bin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
