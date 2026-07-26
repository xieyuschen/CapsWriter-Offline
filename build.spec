# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller：将 Client、Server 与托盘打包为一个 CapsWriter.exe。"""

from os import makedirs, walk
from os.path import basename, dirname, exists, join
from shutil import copyfile

from PyInstaller.utils.hooks import collect_all


binaries = []
datas = []
hiddenimports = [
    "websockets",
    "websockets.client",
    "websockets.server",
    "rich",
    "rich.console",
    "rich.markdown",
    "rich._unicode_data.unicode17-0-0",
    "keyboard",
    "pynput",
    "pyclip",
    "numpy",
    "numba",
    "sounddevice",
    "pypinyin",
    "watchdog",
    "typer",
    "srt",
    "rapidfuzz",
    "sherpa_onnx",
    "gguf",
    "PIL",
    "PIL.Image",
    "pystray",
]

# 模型后端和托盘均包含延迟加载的本地库，显式收集能避免开发机可用、
# 冻结后缺 DLL 的情况。
for package in ("sherpa_onnx", "onnxruntime", "gguf", "PIL"):
    try:
        package_datas, package_binaries, package_hiddenimports = collect_all(package)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hiddenimports
    except Exception as exc:
        print(f"[WARN] 无法显式收集 {package}: {exc}")

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
        "funasr",
        "pydantic",
        "torch",
    ],
    noarchive=True,
)

# 排除开发机 CUDA 文件；DirectML 保留，作为上游支持的 Windows GPU 后端。
filtered_binaries = []
for name, source, binary_type in analysis.binaries:
    source_lower = source.lower() if isinstance(source, str) else ""
    is_system_cuda = (
        "\\nvidia gpu computing toolkit\\cuda\\" in source_lower
        or "\\nvidia\\cudnn\\" in source_lower
        or ("\\cuda\\v" in source_lower and "\\bin\\" in source_lower)
    )
    is_cuda_provider = "onnxruntime_providers_cuda.dll" in name.lower()
    if not is_system_cuda and not is_cuda_provider:
        filtered_binaries.append((name, source, binary_type))
analysis.binaries = filtered_binaries

# 配置和 core 源码保留在发行目录，方便用户直接编辑并跟随上游结构。
private_modules = ["core", "config_client", "config_server", "LLM"]
analysis.pure = [
    entry
    for entry in analysis.pure
    if not any(
        entry[0] == module or entry[0].startswith(module + ".")
        for module in private_modules
    )
]
analysis.datas = [
    entry
    for entry in analysis.datas
    if not any(
        entry[0].startswith(module + "/")
        or entry[0].startswith(module + "\\")
        or entry[0] in (module + ".py", module + ".pyc")
        for module in private_modules
    )
]

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
    "config_client.py",
    "config_server.py",
    "hot.txt",
    "hot-server.txt",
    "hot-rule.txt",
    "readme.md",
    "LICENSE",
]
extra_folders = ["assets", "core", "LLM", "docs"]
destination_root = join("dist", basename(collection.name))

for folder in extra_folders:
    if not exists(folder):
        continue
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

# 模型单独下载；发行包只创建明确的目标目录和说明。
models_directory = join(destination_root, "models")
makedirs(models_directory, exist_ok=True)
model_note = join(models_directory, "请将模型文件放在此目录.txt")
with open(model_note, "w", encoding="utf-8") as note:
    note.write(
        "模型下载与目录结构见 readme.md，或访问：\n"
        "https://github.com/HaujetZhao/CapsWriter-Offline/releases/tag/models\n"
    )
