"""Lance et surveille llama-server.exe (moteur local du modèle Qwen)."""
import atexit
import logging
import socket
import subprocess
import time
from pathlib import Path

import httpx
import psutil

from raya.config import chemin_llama_server

log = logging.getLogger(__name__)

# Les consignes et les outils occupent déjà ~5 000 tokens : avec 8 192, il ne restait de la place que pour
# deux longues réponses. 16 384 coûte ~250 Mo de mémoire vive de plus (mesuré avec le modèle 4B).
TAILLE_CONTEXTE = 16384
# Une capture d'écran coûte au plus ce nombre de tokens (sur les 16 384 du contexte)
MAX_TOKENS_IMAGE = 1024


def _port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _lier_a_raya(proc: subprocess.Popen):
    """Place le processus dans un « job » Windows : il s'arrête automatiquement si Raya
    se ferme, même brutalement (plantage, Gestionnaire des tâches)."""
    import ctypes
    from ctypes import wintypes

    class Limites(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class LimitesEtendues(ctypes.Structure):
        _fields_ = [("Basique", Limites), ("IoInfo", ctypes.c_uint64 * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel32.CreateJobObjectW(None, None)
    infos = LimitesEtendues()
    infos.Basique.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(job, 9, ctypes.byref(infos), ctypes.sizeof(infos)) and \
        kernel32.AssignProcessToJobObject(job, int(proc._handle))
    if not ok:
        log.warning("Impossible de lier llama-server à Raya (erreur %s)", ctypes.get_last_error())
    return job  # le job doit rester ouvert tant que Raya tourne


def _tuer_orphelins(exe: Path) -> None:
    """Arrête un llama-server resté ouvert après un plantage précédent de Raya."""
    cible = str(exe).lower()
    for p in psutil.process_iter(["exe"]):
        try:
            if (p.info["exe"] or "").lower() == cible:
                p.kill()
        except (psutil.Error, OSError):
            pass


class ServeurLLM:
    def __init__(self, modele: Path, vision: Path | None = None):
        self.modele = modele
        self.vision = vision  # module de vision (mmproj) : sans lui, Raya ne peut pas regarder l'écran
        self.port = 0
        self._proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def demarrer(self, delai_max: float = 180) -> None:
        exe = chemin_llama_server()
        if not exe.exists():
            raise FileNotFoundError(f"Moteur introuvable : {exe}")
        if not self.modele.exists():
            raise FileNotFoundError(f"Modèle introuvable : {self.modele}")
        _tuer_orphelins(exe)
        self.port = _port_libre()
        threads = max(2, (psutil.cpu_count(logical=False) or 4))
        cmd = [
            str(exe),
            "-m", str(self.modele),
            "--host", "127.0.0.1",
            "--port", str(self.port),
            "-c", str(TAILLE_CONTEXTE),
            "--parallel", "1",  # une seule conversation à la fois : tout le contexte pour elle
            "-t", str(threads),
            "--jinja",
            "--no-webui",
        ]
        if self.vision:
            cmd += ["--mmproj", str(self.vision), "--image-max-tokens", str(MAX_TOKENS_IMAGE)]
        log.info("Démarrage llama-server : %s", " ".join(cmd))
        self._proc = subprocess.Popen(
            cmd,
            cwd=exe.parent,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self._job = _lier_a_raya(self._proc)
        atexit.register(self.arreter)
        self._attendre_pret(delai_max)

    def _attendre_pret(self, delai_max: float) -> None:
        fin = time.monotonic() + delai_max
        while time.monotonic() < fin:
            if self._proc and self._proc.poll() is not None:
                raise RuntimeError("Le moteur IA s'est arrêté au démarrage.")
            try:
                if httpx.get(f"{self.url}/health", timeout=2).status_code == 200:
                    log.info("llama-server prêt sur le port %s", self.port)
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise TimeoutError("Le moteur IA met trop de temps à démarrer.")

    def arreter(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
