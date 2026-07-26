# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build for the unified client + server tray application."""

from os import makedirs, walk
from os.path import basename, dirname, exists, join
from pathlib import Path
from shutil import copyfile

from PyInstaller.utils.hooks import collect_all, get_package_paths


binaries = []
hiddenimports = []
datas = []

# onnxruntime ships native providers that aren't always discovered from the
# lazy imports in the recognition process.
# Keep the native providers. Importing every onnxruntime tool as a hidden
# module would pull unrelated quantization and transformer utilities into the
# desktop build.
_onnx_data, onnx_binaries, _onnx_hiddenimports = collect_all("onnxruntime")
binaries += onnx_binaries

analysis = Analysis(
    ["start_capswriter.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["build_hook.py"],
    excludes=[
        "IPython",
        "PySide6",
        "PySide2",
        "PyQt5",
        "matplotlib",
        "wx",
        "torch",
    ],
    noarchive=False,
)

# Locate sherpa's compatible native library. PyInstaller may flatten funasr's
# older copy with the same filename to the application root.
_package_root, sherpa_package_dir = get_package_paths("sherpa_onnx")
sherpa_library_dir = Path(sherpa_package_dir) / "lib"

# Keep application modules outside the archive so config.py and hot-word files
# remain editable in the packaged folder, matching the project's existing
# distribution format.
private_modules = ["util", "config", "core_server", "core_client"]
pure_modules = analysis.pure.copy()
analysis.pure.clear()
for name, source, module_type in pure_modules:
    is_private = any(
        name == module or name.startswith(module + ".")
        for module in private_modules
    )
    if not is_private:
        analysis.pure.append((name, source, module_type))

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="CapsWriter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["assets\\icon.ico"],
    contents_directory="internal",
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CapsWriter-Offline",
)

extra_files = [
    "config.py",
    "core_server.py",
    "core_client.py",
    "hot-en.txt",
    "hot-zh.txt",
    "hot-rule.txt",
    "keywords.txt",
    "readme.md",
]
extra_folders = ["assets", "util"]
destination_root = join("dist", basename(collection.name))

# Replace the flattened conflicting library after COLLECT resolves symlinks.
# Without this, the frozen model child fails with an undefined Whisper feature
# symbol even though the same dependencies work when run from source.
internal_directory = Path(destination_root) / "internal"
if sherpa_library_dir.is_dir():
    for sherpa_copy in sherpa_library_dir.iterdir():
        if "kaldi-native-fbank-core" not in sherpa_copy.name.lower():
            continue
        flattened_copy = internal_directory / sherpa_copy.name
        if flattened_copy.exists() or flattened_copy.is_symlink():
            flattened_copy.unlink()
        copyfile(sherpa_copy, flattened_copy)

for folder in extra_folders:
    for directory, _subdirectories, filenames in walk(folder):
        for filename in filenames:
            if filename.endswith((".pyc", ".pyo")) or "__pycache__" in directory:
                continue
            extra_files.append(join(directory, filename))

for source in extra_files:
    if not exists(source):
        continue
    destination = join(destination_root, source)
    makedirs(dirname(destination), exist_ok=True)
    copyfile(source, destination)

# Models remain a separate download because they are over 1 GB. Creating the
# directory in every build makes the expected destination unambiguous.
models_directory = join(destination_root, "models")
makedirs(models_directory, exist_ok=True)
model_note = join(models_directory, "请将模型文件放在此目录.txt")
with open(model_note, "w", encoding="utf-8") as file:
    file.write(
        "需要 paraformer-offline-zh 和 punc_ct-transformer_cn-en 两个模型目录。\n"
        "详见上一级 readme.md。\n"
    )
