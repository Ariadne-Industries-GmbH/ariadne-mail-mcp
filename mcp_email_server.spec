# Build on each target OS: uv run pyinstaller --noconfirm --clean mcp_email_server.spec
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules, copy_metadata

datas = []
binaries = []
hiddenimports = ['anyio', 'starlette.routing']
# Numpy's dispatcher must be initialized once with all extensions available.
d, b, h = collect_all('numpy')
datas += d
binaries += b
hiddenimports += h
for package in ('gradio', 'gradio_client', 'safehttpx', 'groovy'):
    datas += collect_data_files(package)
for package in ('gradio', 'mcp', 'keyring'):
    datas += copy_metadata(package, recursive=True)
hiddenimports += collect_submodules('gradio')
hiddenimports += collect_submodules('keyring.backends')
datas += collect_data_files('mcp_email_server', includes=['*-setup.md', 'oauth-clients.json'])

a = Analysis(
    ['main.py'], pathex=[], binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=['rthook_no_pyi.py'],
    excludes=['pytest', 'ruff', 'nuitka', 'IPython', 'matplotlib'],
    noarchive=False, optimize=0, module_collection_mode={'gradio': 'py', 'groovy': 'py'},
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='ariadne-mail-mcp',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    runtime_tmpdir=None, console=True, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None,
)
