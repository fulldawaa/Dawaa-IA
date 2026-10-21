# -*- mode: python ; coding: utf-8 -*-
# Construction : .venv\Scripts\pyinstaller raya.spec --noconfirm
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

racine = Path(SPECPATH)

datas = [
    (str(racine / "raya" / "ui"), "raya/ui"),
    (str(racine / "assets"), "assets"),
]
binaries = []
hiddenimports = ["pystray._win32", "pynput.keyboard._win32", "pynput.mouse._win32"]

# llama-server : uniquement le serveur et ses bibliothèques (pas les autres outils de llama.cpp)
llama = racine / "vendor" / "llama"
for f in llama.iterdir():
    if f.suffix.lower() == ".dll" or f.name == "llama-server.exe" or f.name.startswith("LICENSE"):
        binaries.append((str(f), "vendor/llama"))
# Runtime Visual C++ à côté de llama-server : sur un PC neuf il peut manquer (redistribution locale autorisée)
system32 = Path(os.environ["SYSTEMROOT"]) / "System32"
for dll in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
    binaries.append((str(system32 / dll), "vendor/llama"))

for paquet in ("faster_whisper", "ctranslate2", "onnxruntime", "webview", "trafilatura", "justext",
               "courlan", "htmldate", "dateparser", "edge_tts", "primp", "ddgs"):
    d, b, h = collect_all(paquet)
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files("certifi")

a = Analysis(
    [str(racine / "lancer_raya.py")],
    pathex=[str(racine)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "torch", "tensorflow", "hf_xet", "pefile"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Raya",
    icon=str(racine / "assets" / "raya.ico"),
    console=False,
    version=str(racine / "installeur" / "version.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Raya")
