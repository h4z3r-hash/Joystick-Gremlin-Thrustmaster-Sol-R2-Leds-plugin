#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server2p.py — SOL-R2 light server (INDEX header, alias) + timing controls

Aggiunte:
- --tx-delay-ms <ms> : attende tra i pacchetti per device (default 0)
- --repeat <n>       : ripete l'invio di ogni pacchetto n volte (default 1)
- --usb-timeout-ms   : timeout di write USB (default 1000)
- --max-entries <m>  : max (ADDR,R,G,B) per pacchetto (default 15 -> 4+4*m <= 64)

Mantiene:
- Formato pacchetto: INDEX(4) + (ADDR,R,G,B)*N
- Raggruppo per INDEX (LED11 separato)
- Alias: LED9 -> 9A..9H, LED10 -> 10A..10C
- --debug: log RX e payload per device

Estensioni effetti:
- Comandi supportati:
    [left:|right:]LEDx R G B
    [left:|right:]LEDx R G B BLINK <ms>
    [left:|right:]LEDx R G B FADE  <ms>
    [left:|right:]LEDx R G B RAINBOW <ms>
  BLINK: colore ON/OFF ogni <ms> (mezzo periodo)
  FADE : fade in/out continuo sul colore indicato con periodo <ms>
  RAINBOW: ciclo di tinta (hue) HSV con periodo <ms> (luminosità dal colore base)
- Per fermare un effetto: invia un comando senza effetto sullo stesso LED,
  es. "LED1 0 0 0" oppure "LED1 0 255 0".
"""

import argparse, json, socketserver, threading, time, traceback
from typing import Dict, Tuple, List, Optional
import colorsys

# --------------------- Config ---------------------
VID = 0x044F
PID_RIGHT = 0x0422
PID_LEFT  = 0x042A
USB_INTERFACE_DEFAULT = 1
USB_EP_OUT_DEFAULT    = 0x02

LISTEN_HOST_DEFAULT   = "0.0.0.0"
LISTEN_PORT_DEFAULT   = 8766

# --------------------- MAP integrata ---------------------
EMBED_MAP: Dict[str, Tuple[str, str]] = {
    "LED1":   ("11", "01 08 05 FF"),
    "LED2":   ("10", "01 08 05 FF"),
    "LED3":   ("12", "01 08 05 FF"),
    "LED4":   ("13", "01 08 05 FF"),
    "LED5":   ("08", "01 08 05 FF"),
    "LED6":   ("07", "01 08 05 FF"),
    "LED7":   ("09", "01 08 05 FF"),
    "LED8":   ("0A", "01 08 05 FF"),
    "LED9A":  ("04", "01 08 05 FF"),
    "LED9B":  ("05", "01 08 05 FF"),
    "LED9C":  ("06", "01 08 05 FF"),
    "LED9D":  ("0B", "01 08 05 FF"),
    "LED9E":  ("0C", "01 08 05 FF"),
    "LED9F":  ("0D", "01 08 05 FF"),
    "LED9G":  ("0E", "01 08 05 FF"),
    "LED9H":  ("0F", "01 08 05 FF"),
    "LED10A": ("01", "01 08 05 FF"),
    "LED10B": ("02", "01 08 05 FF"),
    "LED10C": ("03", "01 08 05 FF"),
    "LED11":  ("00", "01 88 01 FF"),
}

class LEDMap:
    def __init__(self, m: Dict[str, Tuple[str, str]]):
        lm: Dict[str, Tuple[int, bytes]] = {}
        for k, (addr_hex, idx_hex) in m.items():
            k_up = k.upper()
            addr = int(addr_hex, 16)
            idx_bytes = bytes(int(t, 16) for t in idx_hex.split())
            if len(idx_bytes) != 4:
                raise ValueError(f"INDEX deve essere 4 byte per {k}")
            lm[k_up] = (addr, idx_bytes)
        self._m = lm

    def get(self, name: str) -> Tuple[int, bytes]:
        key = name.upper()
        if key not in self._m:
            raise KeyError(f"LED non definito: {name}")
        return self._m[key]

    def size(self) -> int:
        return len(self._m)

    def example(self):
        k = next(iter(self._m))
        return k, self._m[k]

    def keys(self) -> List[str]:
        """Ritorna la lista dei nomi LED conosciuti."""
        return list(self._m.keys())


LED_MAP = LEDMap(EMBED_MAP)

# --------------------- Alias/gruppi ---------------------
GROUP_ALIASES = {
    "LED9":  ["LED9A","LED9B","LED9C","LED9D","LED9E","LED9F","LED9G","LED9H"],
    "LED10": ["LED10A","LED10B","LED10C"],
}
def expand_leds(led_name: str) -> List[str]:
    key = led_name.upper()
    return GROUP_ALIASES.get(key, [key])

# --------------------- USB backend ---------------------
try:
    import usb.core as usb_core
    import usb.util as usb_util
    HAVE_USB = True
except Exception:
    usb_core = None
    usb_util = None
    HAVE_USB = False

class USBDevice:
    def __init__(self, vid: int, pid: int, name: str, interface: int, ep_out: int, timeout_ms: int, dry_run: bool = False, debug: bool=False):
        self.vid = vid; self.pid = pid; self.name = name
        self.intf = interface; self.ep = ep_out
        self.lock = threading.Lock(); self.dev = None
        self.timeout_ms = timeout_ms
        self.dry_run = dry_run; self.debug = debug

    def open(self):
        if self.dry_run:
            print(f"[USB:DRY] {self.name} simulato (VID=0x{self.vid:04X}, PID=0x{self.pid:04X})")
            return
        if not HAVE_USB:
            raise RuntimeError("PyUSB non disponibile: usa --dry-run o installa pyusb")
        self.dev = usb_core.find(idVendor=self.vid, idProduct=self.pid)
        if self.dev is None:
            raise RuntimeError(f"{self.name}: device non trovato (VID=0x{self.vid:04X}, PID=0x{self.pid:04X})")
        try:
            self.dev.set_configuration()
        except Exception:
            pass
        try:
            if self.dev.is_kernel_driver_active(self.intf):
                self.dev.detach_kernel_driver(self.intf)
        except Exception:
            pass
        usb_util.claim_interface(self.dev, self.intf)
        print(f"[USB] {self.name} aperto su IF={self.intf}, EP_OUT=0x{self.ep:02X}, timeout={self.timeout_ms}ms")

    def close(self):
        if self.dry_run or not HAVE_USB:
            return
        try:
            if self.dev:
                usb_util.release_interface(self.dev, self.intf)
        except Exception:
            pass

    def write(self, data: bytes):
        if self.dry_run or self.debug:
            print(f"[USB:{'DRY:' if self.dry_run else ''}{self.name}] ({len(data)}B) {data.hex(' ').upper()}")
        if self.dry_run:
            return
        n = self.dev.write(self.ep, data, timeout=self.timeout_ms)
        if n != len(data):
            raise IOError(f"{self.name}: scritto {n}/{len(data)} bytes")

# --------------------- Util ---------------------
def parse_command_line(line: str) -> Tuple[Optional[str], str, int, int, int]:
    raw = line.strip("\r\n")
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        raw = raw[1:-1]
    raw = raw.strip()
    if raw == "":
        raise ValueError("Riga vuota.")
    side: Optional[str] = None
    lraw = raw.lower()
    if lraw.startswith("left:"):
        side, raw = "left", raw[5:].strip()
    elif lraw.startswith("right:"):
        side, raw = "right", raw[6:].strip()
    parts = raw.replace(",", " ").split()
    if len(parts) != 4:
        raise ValueError("Formato: [left:|right:]LEDx R G B")
    led_name = parts[0].upper()
    r, g, b = (int(parts[1]), int(parts[2]), int(parts[3]))
    for v in (r, g, b):
        if not (0 <= v <= 255):
            raise ValueError("R,G,B devono essere tra 0..255")
    return side, led_name, r, g, b


def strip_effect_suffix(raw: str) -> Tuple[str, Optional[str], int]:
    """
    Se alla fine della riga c'è 'BLINK <ms>', 'FADE <ms>' o 'RAINBOW <ms>'
    li rimuove e restituisce:
        (riga_senza_effetto, effetto, periodo_ms)

    Se non trova un effetto valido, ritorna (raw, None, 0).
    """
    s = raw.strip()
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        s = s[1:-1]
    tokens = s.replace(",", " ").split()
    if len(tokens) >= 6:
        mode_token = tokens[-2].upper()
        period_token = tokens[-1]
        if mode_token in ("BLINK", "FADE", "RAINBOW"):
            try:
                period_ms = int(period_token)
            except ValueError:
                period_ms = 0
            core_tokens = tokens[:-2]
            core_line = " ".join(core_tokens)
            return core_line, mode_token, period_ms
    return raw, None, 0


def build_entry(led_name: str, r: int, g: int, b: int) -> Tuple[bytes, bytes]:
    addr, idx = LED_MAP.get(led_name)
    return idx, bytes([addr, r, g, b])

def pack_by_index(entries: List[Tuple[bytes, bytes]], max_entries: int) -> List[bytes]:
    """
    Raggruppa per INDEX e crea pacchetti: INDEX4 + (ADDR,R,G,B)*n, con n<=max_entries,
    cosi' ogni pacchetto resta entro 4 + 4*n <= 64.
    """
    from collections import defaultdict
    groups: Dict[bytes, List[bytes]] = defaultdict(list)
    for idx, argb in entries:
        groups[idx].append(argb)

    packets: List[bytes] = []
    for idx, lst in groups.items():
        i = 0
        while i < len(lst):
            n = min(max_entries, len(lst) - i)
            chunk = idx + b"".join(lst[i:i+n])
            packets.append(chunk)
            i += n
    return packets

# --------------------- Stato LED e loop di streaming (vecchia versione, non usata) ---------------------
class LEDStateOld:
    """
    Mantiene lo stato corrente (R,G,B) di ogni LED per lato (left/right)
    in modo thread-safe. Il server TCP aggiorna questo stato in base ai
    comandi ricevuti, mentre un thread separato invia continuamente lo
    stato verso i dispositivi USB.
    """
    def __init__(self, led_names: Optional[List[str]] = None):
        self._lock = threading.Lock()
        # chiave: (side, led_name) dove side in {"left","right"}
        self._state: Dict[Tuple[Optional[str], str], Tuple[int, int, int]] = {}
        if led_names:
            for name in led_names:
                name_up = name.upper()
                # inizializza tutto spento
                self._state[("left",  name_up)] = (0, 0, 0)
                self._state[("right", name_up)] = (0, 0, 0)

    def set(self, side: Optional[str], led_name: str, r: int, g: int, b: int) -> None:
        name_up = led_name.upper()
        s = side.lower() if isinstance(side, str) and side is not None else None
        with self._lock:
            if s is None:
                # BOTH / nessun prefisso: aggiorna entrambi i lati
                self._state[("left",  name_up)] = (r, g, b)
                self._state[("right", name_up)] = (r, g, b)
            elif s in ("left", "right"):
                self._state[(s, name_up)] = (r, g, b)

    def snapshot(self) -> Dict[Tuple[Optional[str], str], Tuple[int, int, int]]:
        with self._lock:
            # copia shallow sufficiente (i valori sono tuple immutabili)
            return dict(self._state)


# --------------------- Stato LED e streaming opzionale (versione attuale con priorità + effetti) ---------------------
class LEDState:
    """
    Mantiene lo stato corrente di ogni LED per lato, con una nozione di priorità.
    _state[(side, led_name)] = (r, g, b, priority)
    """

    def __init__(self, led_names: Optional[List[str]] = None):
        self._lock = threading.Lock()
        self._state: Dict[Tuple[str, str], Tuple[int, int, int, int]] = {}
        if led_names:
            for name in led_names:
                n = name.upper()
                # Inizializza sia left che right a spento, priorità 0
                self._state[("left", n)] = (0, 0, 0, 0)
                self._state[("right", n)] = (0, 0, 0, 0)

    def set(self, side: Optional[str], led_name: str,
            r: int, g: int, b: int, priority: int) -> bool:
        """
        Aggiorna il colore memorizzato se la priorità è >= di quella esistente.
        Restituisce True se l'update viene accettato (e quindi va inviato via USB),
        False se viene ignorato (es. un loop che prova a sovrascrivere un override).
        """
        led = led_name.upper()
        side_norm = side.lower() if isinstance(side, str) and side is not None else None

        def _update_for_side(skey: str) -> bool:
            key = (skey, led)
            cur = self._state.get(key, (0, 0, 0, 0))
            _, _, _, cur_prio = cur
            if priority < cur_prio:
                # Priorità più bassa: ignora
                return False
            new_prio = priority
            # Convenzione: override (priority>0) con RGB=(0,0,0) rilascia il LED al loop
            if priority > 0 and r == 0 and g == 0 and b == 0:
                new_prio = 0
            self._state[key] = (r, g, b, new_prio)
            return True

        updated = False
        with self._lock:
            if side_norm is None:
                # BOTH: applica a left e right
                for skey in ("left", "right"):
                    if _update_for_side(skey):
                        updated = True
            elif side_norm in ("left", "right"):
                updated = _update_for_side(side_norm)
        return updated

    def snapshot(self) -> Dict[Tuple[str, str], Tuple[int, int, int]]:
        """Ritorna una copia (side, led) -> (r,g,b) senza i livelli di priorità."""
        with self._lock:
            return {(side, led): (r, g, b)
                    for (side, led), (r, g, b, _prio) in self._state.items()}


class EffectRegistry:
    """
    Gestisce gli effetti dinamici (BLINK/FADE/RAINBOW) per ogni LED per lato.

    _effects[(side, led)] = (mode, period_ms, start_time, (r,g,b), priority)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._effects: Dict[Tuple[str, str], Tuple[str, int, float, Tuple[int, int, int], int]] = {}

    def set_effect(self, side: Optional[str], led_name: str,
                   mode: Optional[str], period_ms: int,
                   base_rgb: Tuple[int, int, int], priority: int) -> None:
        """
        Imposta o cancella l'effetto per il LED indicato.

        - mode None                 => rimuove l'effetto
        - mode "BLINK"/"FADE"/"RAINBOW" => salva effetto con priorità `priority`
        """
        led_up = led_name.upper()
        if side is None:
            sides = ["left", "right"]
        else:
            s = side.lower()
            if s not in ("left", "right"):
                return
            sides = [s]

        with self._lock:
            for s in sides:
                key = (s, led_up)
                if mode is None:
                    self._effects.pop(key, None)
                    continue
                cur = self._effects.get(key)
                cur_prio = cur[4] if cur is not None else 0
                if priority < cur_prio:
                    # Non sovrascrivere un effetto di priorità maggiore
                    continue
                self._effects[key] = (
                    mode,
                    max(1, period_ms),
                    time.monotonic(),
                    base_rgb,
                    priority,
                )

    def apply(self, side: str, led_name: str,
              base_rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
        """
        Ritorna il colore da inviare tenendo conto dell'effetto (se presente).
        """
        led_up = led_name.upper()
        key = (side, led_up)
        with self._lock:
            eff = self._effects.get(key)
        if not eff:
            return base_rgb

        mode, period_ms, t0, eff_rgb, _prio = eff
        r0, g0, b0 = eff_rgb

        if mode == "BLINK":
            if period_ms <= 0:
                return eff_rgb
            # half_period: tempo acceso/spento. Esempio: 500ms => 500 ON, 500 OFF.
            half_period = period_ms / 1000.0
            phase = int((time.monotonic() - t0) / half_period)
            on = (phase % 2) == 0
            return eff_rgb if on else (0, 0, 0)

        if mode == "FADE":
            if period_ms <= 0:
                return eff_rgb
            period_s = period_ms / 1000.0
            pos = (time.monotonic() - t0) % period_s
            frac = pos / period_s
            # onda triangolare 0..1..0
            if frac < 0.5:
                k = frac * 2.0
            else:
                k = (1.0 - frac) * 2.0
            return (int(r0 * k), int(g0 * k), int(b0 * k))

        if mode == "RAINBOW":
            # Ciclo di hue HSV 0..1 con periodo "period_ms".
            # Luminosità presa dal max componente del colore base (se tutto 0, usiamo 1.0).
            if period_ms <= 0:
                period_ms = 1000
            period_s = period_ms / 1000.0
            pos = (time.monotonic() - t0) % period_s
            h = pos / period_s  # 0..1
            base_val = max(r0, g0, b0) / 255.0
            if base_val <= 0.0:
                base_val = 1.0
            r_f, g_f, b_f = colorsys.hsv_to_rgb(h, 1.0, base_val)
            return (int(r_f * 255), int(g_f * 255), int(b_f * 255))

        # fallback: nessun effetto speciale
        return eff_rgb



def stream_worker(server: "ThreadedTCPServer"):
    """
    Thread opzionale che invia periodicamente solo i LED che cambiano.
    - Usa server.led_state come sorgente dei colori "base".
    - Applica eventuali effetti BLINK/FADE/RAINBOW dall'EffectRegistry.
    - Non invia nulla se non ci sono differenze rispetto al frame precedente.
    - Se non arrivano comandi dal client per stream_idle_timeout_ms e
      NON ci sono effetti attivi, lo stream va in idle.
      Se invece ci sono effetti attivi, continua all'infinito (finché non
      vengono cancellati con un comando STATIC).
    """
    interval_ms = getattr(server, "stream_interval_ms", 0)
    if interval_ms <= 0:
        return

    max_entries = getattr(server, "max_entries", 15)
    debug = getattr(server, "debug", False)

    # stato del frame precedente dopo l'applicazione degli effetti
    prev_frame: Dict[Tuple[Optional[str], str], Tuple[int, int, int]] = {}

    try:
        while not getattr(server, "stream_stop", False):
            idle_ms = getattr(server, "stream_idle_timeout_ms", 0)
            last_rx = getattr(server, "last_rx_ts", None)
            now = time.monotonic()

            # Controllo inattività:
            # - se è passato troppo tempo dall'ultima RX
            # - e NON ci sono effetti attivi -> vai in idle
            # - se invece ci sono effetti attivi, continui a streammare
            effects_reg: Optional[EffectRegistry] = getattr(server, "effects", None)
            any_effects = False
            if effects_reg is not None:
                try:
                    with effects_reg._lock:
                        any_effects = bool(effects_reg._effects)
                except Exception:
                    any_effects = False

            if idle_ms > 0 and last_rx is not None and not any_effects:
                if (now - last_rx) * 1000.0 > idle_ms:
                    if debug:
                        print(f"[STRM] idle da {int((now - last_rx)*1000)} ms -> nessun invio (no effects)")
                    prev_frame.clear()
                    time.sleep(interval_ms / 1000.0)
                    continue

            snap = server.led_state.snapshot()
            effects: Optional[EffectRegistry] = getattr(server, "effects", None)

            entries_both: List[Tuple[bytes, bytes]] = []
            entries_left: List[Tuple[bytes, bytes]] = []
            entries_right: List[Tuple[bytes, bytes]] = []

            # nuovo frame dopo applicazione effetti
            cur_frame: Dict[Tuple[Optional[str], str], Tuple[int, int, int]] = {}

            for (side, led), (r, g, b) in snap.items():
                base_rgb = (r, g, b)

                # Applica eventuale effetto
                if effects is not None and side in ("left", "right"):
                    r, g, b = effects.apply(side, led, base_rgb)

                rgb = (r, g, b)
                key = (side, led)
                cur_frame[key] = rgb

                # Se il colore (dopo effetto) è identico al frame precedente,
                # non c'è bisogno di inviare nulla per questo LED.
                prev_rgb = prev_frame.get(key)
                if prev_rgb is not None and prev_rgb == rgb:
                    continue

                # Da qui in poi il LED è effettivamente cambiato: includiamo
                # l'aggiornamento nel pacchetto, anche se è (0,0,0) per lo spegnimento.
                for lname in expand_leds(led):
                    try:
                        idx, argb = build_entry(lname, r, g, b)
                    except KeyError:
                        continue
                    if side == "left":
                        entries_left.append((idx, argb))
                    elif side == "right":
                        entries_right.append((idx, argb))
                    else:
                        entries_both.append((idx, argb))

            # Aggiorna il frame precedente
            prev_frame = cur_frame

            # Se niente è cambiato, aspettiamo solo il prossimo tick.
            if not entries_both and not entries_left and not entries_right:
                time.sleep(interval_ms / 1000.0)
                continue

            packets_both  = pack_by_index(entries_both,  max_entries=max_entries)
            packets_left  = pack_by_index(entries_left,  max_entries=max_entries)
            packets_right = pack_by_index(entries_right, max_entries=max_entries)

            if debug:
                for dev_name, plist in (("BOTH", packets_both),
                                        ("LEFT", packets_left),
                                        ("RIGHT", packets_right)):
                    for p in plist:
                        idx_hex = p[:4].hex(" ").upper()
                        n = (len(p) - 4) // 4
                        print(f"[STRM] PACK {dev_name}: len={len(p)} index=[{idx_hex}] entries={n}  HEX={p.hex(' ').upper()}")

            # Invio vero e proprio
            if packets_both:
                server.devices.send_packets(packets_both, None)
            if packets_left:
                server.devices.send_packets(packets_left, "left")
            if packets_right:
                server.devices.send_packets(packets_right, "right")

            time.sleep(interval_ms / 1000.0)
    except Exception:
        traceback.print_exc()

# --------------------- Dispositivi ---------------------
class Devices:
    def __init__(self, interface: int, ep_out: int, timeout_ms: int, tx_delay_ms: int, repeat: int, dry_run: bool, debug: bool):
        self.right = USBDevice(VID, PID_RIGHT, "RIGHT", interface, ep_out, timeout_ms, dry_run, debug)
        self.left  = USBDevice(VID, PID_LEFT,  "LEFT",  interface, ep_out, timeout_ms, dry_run, debug)
        self.debug = debug
        self.tx_delay_ms = tx_delay_ms
        self.repeat = max(1, repeat)

    def open_all(self):
        self.right.open()
        self.left.open()

    def close_all(self):
        self.right.close()
        self.left.close()

    def send_packets(self, packets: List[bytes], side: Optional[str]):
        targets = []
        if side in (None, "right"):
            targets.append(self.right)
        if side in (None, "left"):
            targets.append(self.left)
        for dev in targets:
            for p in packets:
                for _ in range(self.repeat):
                    dev.write(p)
                if self.tx_delay_ms > 0:
                    time.sleep(self.tx_delay_ms/1000.0)

# --------------------- Server TCP ---------------------
class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            # Leggi tutte le righe del comando fino a riga vuota / chiusura
            lines: List[str] = []
            while True:
                ln = self.rfile.readline()
                if not ln:
                    break
                s = ln.decode("utf-8", "ignore")
                if s.strip() == "":
                    break
                lines.append(s)
            if not lines:
                self.wfile.write(b'{"ok": false, "error": "no commands"}\n')
                return

            # Aggiorna il timestamp di ultima RX per il controllo dello streaming
            try:
                self.server.last_rx_ts = time.monotonic()
            except Exception:
                pass

            debug = getattr(self.server, "debug", False)
            if debug:
                for i, l in enumerate(lines, 1):
                    print(f"[RX] {i}: {l.rstrip()}")

            errors: List[str] = []
            effects: Optional[EffectRegistry] = getattr(self.server, "effects", None)

            # Backend USB nativo
            entries_both: List[Tuple[bytes, bytes]] = []
            entries_left: List[Tuple[bytes, bytes]] = []
            entries_right: List[Tuple[bytes, bytes]] = []

            led_state: Optional[LEDState] = getattr(self.server, "led_state", None)

            for s in lines:
                try:
                    core_line, mode, period_ms = strip_effect_suffix(s)
                    side, led_name, r, g, b = parse_command_line(core_line)

                    # PRIORITY:
                    # - BLINK / FADE / RAINBOW => priority = 1
                    # - STATIC                 => priority = 2 (può sovrascrivere gli effetti)
                    if mode in ("BLINK", "FADE", "RAINBOW"):
                        priority = 1
                    else:
                        priority = 2

                    for lname in expand_leds(led_name):
                        accept = True
                        if led_state is not None:
                            accept = led_state.set(side, lname, r, g, b, priority)
                        if not accept:
                            # Es. comando di priorità più bassa rispetto allo stato corrente
                            continue

                        # Gestione effetti: BLINK/FADE/RAINBOW oppure clear se mode è None
                        if effects is not None:
                            effects.set_effect(side, lname, mode, period_ms, (r, g, b), priority)
                            if debug:
                                side_label = "BOTH" if side is None else side.upper()
                                if mode is None:
                                    print(f"[FX] CLEAR {side_label}:{lname}")
                                else:
                                    print(f"[FX] SET {mode} {side_label}:{lname} period={period_ms}ms rgb=({r},{g},{b}) prio={priority}")

                        # Decide se inviare SUBITO il frame o lasciare tutto allo streaming
                        send_immediate = True
                        if mode in ("BLINK", "FADE", "RAINBOW") and getattr(self.server, "stream_interval_ms", 0) > 0:
                            # Se c'è uno stream attivo, per BLINK/FADE/RAINBOW non mandiamo il frame statico
                            # così l'effetto parte da spento e viene gestito dal thread di streaming.
                            send_immediate = False

                        if send_immediate:
                            idx, argb = build_entry(lname, r, g, b)
                            if side is None:
                                entries_both.append((idx, argb))
                            elif side == "left":
                                entries_left.append((idx, argb))
                            elif side == "right":
                                entries_right.append((idx, argb))

                except Exception as e:
                    errors.append(str(e))

            max_entries = getattr(self.server, "max_entries", 15)
            packets_both  = pack_by_index(entries_both,  max_entries=max_entries)
            packets_left  = pack_by_index(entries_left,  max_entries=max_entries)
            packets_right = pack_by_index(entries_right, max_entries=max_entries)

            if debug:
                for dev_name, plist in (("BOTH", packets_both),
                                        ("LEFT", packets_left),
                                        ("RIGHT", packets_right)):
                    for p in plist:
                        idx_hex = p[:4].hex(" ").upper()
                        n = (len(p) - 4) // 4
                        print(f"[DBG] PACK {dev_name}: len={len(p)} index=[{idx_hex}] entries={n}  HEX={p.hex(' ').upper()}")

            # Invio immediato (anche se c'è lo streaming, non dà fastidio)
            devices = getattr(self.server, "devices", None)
            if devices is not None:
                if packets_both:
                    devices.send_packets(packets_both, None)
                if packets_left:
                    devices.send_packets(packets_left, "left")
                if packets_right:
                    devices.send_packets(packets_right, "right")

            resp = {"ok": True}
            if errors:
                resp["skipped"] = errors
            self.wfile.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
        except Exception as e:
            traceback.print_exc()
            err = json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False) + "\n"
            self.wfile.write(err.encode("utf-8"))

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass,
                 devices: Optional[Devices],
                 debug: bool,
                 max_entries: int,
                 stream_interval_ms: int = 0,
                 led_state: Optional[LEDState] = None):
        super().__init__(server_address, RequestHandlerClass)
        self.devices = devices
        self.debug = debug
        self.max_entries = max_entries
        self.stream_interval_ms = stream_interval_ms
        self.led_state = led_state
        # flag globale di stop thread di streaming
        self.stream_stop = False
        # ultimo istante in cui abbiamo ricevuto un comando dal client
        self.last_rx_ts = time.monotonic()
        # timeout di inattività dello stream in ms (può essere sovrascritto da main)
        self.stream_idle_timeout_ms = 3000
        # Registry per effetti BLINK/FADE/RAINBOW
        self.effects = EffectRegistry()



# --------------------- Main ---------------------
def main():
    ap = argparse.ArgumentParser(description="SOL-R2 light server v4 + timing")
    ap.add_argument("--host", default=LISTEN_HOST_DEFAULT)
    ap.add_argument("--port", type=int, default=LISTEN_PORT_DEFAULT)
    ap.add_argument("--iface", type=int, default=USB_INTERFACE_DEFAULT)
    ap.add_argument("--ep", type=lambda x: int(x, 0), default=USB_EP_OUT_DEFAULT)
    ap.add_argument("--usb-timeout-ms", type=int, default=1000)
    ap.add_argument("--tx-delay-ms", type=int, default=0, help="ritardo tra pacchetti per device")
    ap.add_argument("--repeat", type=int, default=1, help="ripeti ogni pacchetto N volte")
    ap.add_argument("--max-entries", type=int, default=15, help="max (ADDR,R,G,B) per pacchetto")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--debug", action="store_true")
    # Streaming opzionale dello stato (0 = disattivato, default)
    ap.add_argument("--stream-interval-ms", type=int, default=0,
                    help="se >0 invia periodicamente lo stato completo dei LED ogni N ms")
    ap.add_argument("--stream-idle-timeout-ms", type=int, default=3000,
                    help="ferma lo stream se non riceve comandi per N ms (default 3000)")

    args = ap.parse_args()

    print(f"[MAP] Caricate {LED_MAP.size()} voci. Esempio: {LED_MAP.example()}")

    # Backend USB nativo
    devices = Devices(interface=args.iface,
                      ep_out=args.ep,
                      timeout_ms=args.usb_timeout_ms,
                      tx_delay_ms=args.tx_delay_ms,
                      repeat=args.repeat,
                      dry_run=args.dry_run,
                      debug=args.debug)
    devices.open_all()

    # Inizializza stato LED (anche se non si usa lo streaming, per la priorità)
    led_state = LEDState(LED_MAP.keys())

    srv = ThreadedTCPServer((args.host, args.port),
                            Handler,
                            devices=devices,
                            debug=args.debug,
                            max_entries=args.max_entries,
                            stream_interval_ms=args.stream_interval_ms,
                            led_state=led_state)

    # Propaga al server il timeout di inattività per lo streaming
    srv.stream_idle_timeout_ms = args.stream_idle_timeout_ms

    # Avvia eventuale thread di streaming
    stream_thread = None
    if args.stream_interval_ms > 0 and devices is not None:
        stream_thread = threading.Thread(target=stream_worker, args=(srv,), daemon=True)
        stream_thread.start()

    # Messaggio di startup
    print(f"[TCP] In ascolto su {args.host}:{args.port}  "
          f"(IF={args.iface}, EP=0x{args.ep:02X}, timeout={args.usb_timeout_ms}ms, "
          f"tx_delay={args.tx_delay_ms}ms, repeat={args.repeat}, "
          f"max_entries={args.max_entries}, debug={args.debug}, "
          f"stream_interval_ms={args.stream_interval_ms})")

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[QUIT] Ctrl+C")
    finally:
        srv.stream_stop = True
        if stream_thread is not None:
            stream_thread.join(timeout=1.0)
        srv.shutdown()
        if devices is not None:
            devices.close_all()


if __name__ == "__main__":
    main()
