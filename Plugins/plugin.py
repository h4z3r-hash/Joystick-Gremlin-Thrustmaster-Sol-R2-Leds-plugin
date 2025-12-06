# plugin.py - Gremlin user plugin to control server.py / server2p.py
# ASCII-only, save as UTF-8.

import os
import shlex
import atexit
import threading
import subprocess

import gremlin
from gremlin.user_plugin import *


# =========================
#  Config di base (fisse)
# =========================

PLUGIN_DIR = os.path.dirname(__file__)

def _detect_server_path():
    """Cerca server.py o server2p.py nella cartella del plugin."""
    candidates = ["server.py", "server2p.py"]
    for name in candidates:
        full = os.path.join(PLUGIN_DIR, name)
        if os.path.isfile(full):
            return full
    return None


# IMPORTANTISSIMO: usa il Python di sistema (quello con PyUSB installato)
DEFAULT_PYTHON = "python"

# Valori “buoni” per il tuo setup (non esposti in UI)
FIXED_TX_DELAY_MS = 0          # --tx-delay-ms
FIXED_REPEAT = 0               # --repeat
FIXED_MAX_ENTRIES = 4          # --max-entries


# =========================
#  Stato processo server
# =========================

_server_proc = [None]
_server_lock = threading.Lock()


def _is_server_running():
    with _server_lock:
        return _server_proc[0] is not None and _server_proc[0].poll() is None


def _build_server_args():
    """
    Costruisce SOLO gli argomenti che vogliamo controllare:
    - tx-delay-ms, repeat, max-entries (fissi)
    - stream-interval-ms, stream-idle-timeout-ms (da UI)
    """
    args = []

    # Fissi
    args.append(f"--tx-delay-ms {FIXED_TX_DELAY_MS}")
    args.append(f"--repeat {FIXED_REPEAT}")
    args.append(f"--max-entries {FIXED_MAX_ENTRIES}")

    # Streaming da UI
    try:
        si = int(stream_interval_ms.value)
    except Exception:
        si = 1
    try:
        idle = int(stream_idle_timeout_ms.value)
    except Exception:
        idle = 3000

    args.append(f"--stream-interval-ms {si}")
    args.append(f"--stream-idle-timeout-ms {idle}")

    return " ".join(args)


def _start_server():
    """
    Avvia server.py/server2p.py se non è già in esecuzione.
    Chiamata solo se "Server on" è True.
    """
    with _server_lock:
        if _server_proc[0] is not None and _server_proc[0].poll() is None:
            try:
                gremlin.util.log("[SOLR2-SRV] Server già in esecuzione.")
            except Exception:
                pass
            return

        srv_path = _detect_server_path()
        if not srv_path:
            msg = (
                "[SOLR2-SRV] Nessun server trovato. "
                "Metti server.py o server2p.py nella stessa cartella del plugin."
            )
            try:
                gremlin.util.log(msg)
            except Exception:
                print(msg)
            return

        py_path = DEFAULT_PYTHON
        srv_args = _build_server_args()

        cmd = [py_path, srv_path] + shlex.split(srv_args, posix=False)

        # Gestione finestra console
        creationflags = 0
        stdout_target = subprocess.DEVNULL
        stderr_target = subprocess.DEVNULL

        hide = False
        try:
            hide = bool(hide_window.value)
        except Exception:
            hide = True

        if hide:
            # Nasconde la finestra su Windows
            if os.name == "nt":
                creationflags = 0x08000000  # CREATE_NO_WINDOW
        else:
            # Mostra la console se possibile
            stdout_target = None
            stderr_target = None

        try:
            _server_proc[0] = subprocess.Popen(
                cmd,
                creationflags=creationflags,
                stdout=stdout_target,
                stderr=stderr_target,
            )
            try:
                gremlin.util.log(f"[SOLR2-SRV] Avvio server: {cmd}")
            except Exception:
                print("[SOLR2-SRV] Avvio server:", cmd)
        except Exception as e:
            try:
                gremlin.util.log(f"[SOLR2-SRV] Errore avvio server: {e}")
            except Exception:
                print("[SOLR2-SRV] Errore avvio server:", e)


def _stop_server():
    """
    Termina server.py/server2p.py se in esecuzione.
    Viene richiamato:
    - quando il profilo / plugin viene fermato (atexit)
    - se "Server on" è False quando il plugin viene caricato/applicato
    """
    with _server_lock:
        if _server_proc[0] is not None and _server_proc[0].poll() is None:
            try:
                _server_proc[0].terminate()
                try:
                    gremlin.util.log("[SOLR2-SRV] Server terminato.")
                except Exception:
                    pass
            except Exception:
                pass
        _server_proc[0] = None


# Quando Gremlin chiude il profilo / esce,
# viene chiamato atexit -> chiudiamo il server.
atexit.register(_stop_server)


def _sync_server_state():
    """
    Sincronizza lo stato del processo con la checkbox "Server on".

    - Se Server on = False -> spegni il server (se acceso).
    - Se Server on = True  -> assicurati che sia acceso.
    """
    try:
        on = bool(server_on.value)
    except Exception:
        on = True

    if not on:
        # Se non deve essere acceso, lo spegniamo sempre.
        _stop_server()
        return

    # Se deve essere acceso, lo avviamo se non è già running.
    if not _is_server_running():
        _start_server()


# =========================
#  Variabili visibili in UI
# =========================

server_on = BoolVariable(
    "Server on",
    "Se spuntato, il server viene avviato e mantenuto attivo.",
    True,
)

stream_interval_ms = IntegerVariable(
    "Stream interval (ms)",
    "Se >0, il server invia periodicamente lo stato completo dei LED ogni N ms.",
    1,      # il valore che hai trovato buono
    0,
    20,
)

stream_idle_timeout_ms = IntegerVariable(
    "Stream idle timeout (ms)",
    "Ferma lo streaming se non riceve comandi per N ms (0 = mai).",
    3000,
    0,
    60000,
)

hide_window = BoolVariable(
    "Hide server console (Windows only)",
    "Nasconde la finestra console del server.",
    True,
)


# =========================
#  Sync all’attivazione / Apply
# =========================

try:
    _sync_server_state()
except Exception as e:
    try:
        gremlin.util.log(f"[SOLR2-SRV] Errore in _sync_server_state: {e}")
    except Exception:
        print("[SOLR2-SRV] Errore in _sync_server_state:", e)
