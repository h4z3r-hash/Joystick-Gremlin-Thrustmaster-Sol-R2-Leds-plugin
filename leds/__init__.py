# -*- coding: utf-8; -*-

import os
import logging
import socket
import re
import time
from xml.etree import ElementTree

from PyQt5 import QtWidgets

from gremlin.base_classes import AbstractAction, AbstractFunctor
from gremlin.common import InputType
import gremlin.ui.input_item

# Logger come nel file funzionante
log = logging.getLogger("system")

# Indirizzo del server LED (uguale a server.py)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766

# Elenco LED, con LED9 e LED10 prima di LED9A / LED10A
LED_NAMES = [
    "LED1", "LED2", "LED3", "LED4", "LED5", "LED6", "LED7", "LED8",
    "LED9",
    "LED9A", "LED9B", "LED9C", "LED9D", "LED9E", "LED9F", "LED9G", "LED9H",
    "LED10",
    "LED10A", "LED10B", "LED10C",
    "LED11",
]

# Effetti supportati lato client (il server li interpreta)
EFFECT_CHOICES = ["STATIC", "BLINK", "FADE", "RAINBOW"]


# ---------------------------------------------------------------------------
# Parte di comunicazione TCP (come nel plugin che funzionava, estesa con effetto)
# ---------------------------------------------------------------------------

def _build_line(led_side, led_name, r, g, b, effect=None, delay_ms=None):
    """Costruisce una singola riga compatibile con server.py.

    Formato base (static):
        [left:|right:]LEDx R G B

    Con effetto:
        [left:|right:]LEDx R G B BLINK 500
        [left:|right:]LEDx R G B FADE 1000
        [left:|right:]LEDx R G B RAINBOW 1500
    """
    s = (led_side or "").strip().upper()
    if s == "LEFT":
        prefix = "left:"
    elif s == "RIGHT":
        prefix = "right:"
    else:  # BOTH o altro -> nessun prefisso
        prefix = ""

    parts = [
        f"{prefix}{led_name}",
        str(int(r)),
        str(int(g)),
        str(int(b)),
    ]

    eff = (effect or "STATIC").upper()
    if eff in ("BLINK", "FADE", "RAINBOW"):
        parts.append(eff)
        # anche 0 è accettato, sarà il server a decidere cosa farne
        if delay_ms is None:
            delay_ms = 0
        parts.append(str(int(delay_ms)))

    return " ".join(parts)


def _send_led(led_side, led_name, r, g, b,
              effect=None, delay_ms=None,
              host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=0.2):
    """Invia il comando LED al server TCP (UN LED per connessione)."""
    line = _build_line(led_side, led_name, r, g, b, effect, delay_ms)
    data = (line + "\n").encode("utf-8")
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.sendall(data)
            s.settimeout(0.05)
            try:
                _ = s.recv(4096)
            except Exception:
                pass
        log.info(f"[LEDs base] TX: {line}")
    except Exception as e:
        log.error(f"[LEDs base] TCP send error: {e}")


def _send_leds_batch(led_side, led_list, r, g, b,
                     effect=None, delay_ms=None,
                     host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=0.2):
    """Invia PIÙ LED in un'unica connessione TCP (tutti insieme)."""
    if not led_list:
        return

    lines = [
        _build_line(led_side, led_name, r, g, b, effect, delay_ms)
        for led_name in led_list
    ]
    payload = ("\n".join(lines) + "\n").encode("utf-8")

    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.sendall(payload)
            s.settimeout(0.05)
            try:
                _ = s.recv(4096)
            except Exception:
                pass
        log.info(f"[LEDs base] TX batch ({len(led_list)}): " + " | ".join(lines))
    except Exception as e:
        log.error(f"[LEDs base] TCP send error (batch): {e}")


# ---------------------------------------------------------------------------
# Parsing espressione LED (LED1,LED2,LED3 e LED1/LED5)
# ---------------------------------------------------------------------------

def _expand_leds_expr(expr: str, default_led: str):
    """
    Espande un'espressione tipo:
      - "LED1,LED2,LED3"
      - "LED1/LED5"  -> LED1,LED2,LED3,LED4,LED5
    Restituisce una lista di nomi LED validi.
    Se l'espressione è vuota o non produce nulla, usa default_led.
    """
    expr = (expr or "").strip()
    leds = []

    if expr:
        # Spezza su virgole, spazi o ';'
        tokens = re.split(r"[,\s;]+", expr)
        for tok in tokens:
            tok = tok.strip()
            if not tok:
                continue

            # Range tipo "LED1/LED5"
            if "/" in tok:
                left, right = tok.split("/", 1)
                left = left.strip().upper()
                right = right.strip().upper()

                m1 = re.match(r"LED(\d+)$", left)
                m2 = re.match(r"LED(\d+)$", right)
                if m1 and m2:
                    n1 = int(m1.group(1))
                    n2 = int(m2.group(1))
                    if n1 <= n2:
                        rng = range(n1, n2 + 1)
                    else:
                        rng = range(n2, n1 + 1)
                    for n in rng:
                        name = f"LED{n}"
                        if name in LED_NAMES and name not in leds:
                            leds.append(name)
                # se non matcha il pattern, ignora questo token
            else:
                # Singolo LED
                name = tok.upper()
                if name in LED_NAMES and name not in leds:
                    leds.append(name)

    if not leds:
        # Fallback: usa il LED singolo
        if default_led in LED_NAMES:
            return [default_led]
        else:
            return ["LED1"]

    return leds


# ---------------------------------------------------------------------------
# Widget: Device + LED singolo + RGB + espressione multi-LED + Effect/Delay + Mode
# ---------------------------------------------------------------------------

class LedsBaseWidget(gremlin.ui.input_item.AbstractActionWidget):
    """
    Widget:
      - combo Device: BOTH / LEFT / RIGHT
      - combo LED singolo: LED1, LED2, ...
      - linea "LEDs Expr": es. "LED1,LED2,LED3" o "LED1/LED5"
      - combo Invio: Tutti insieme / Sequenziale (caterpillar)
      - combo Effect: Static / Blink / Fade / Rainbow
      - spinbox Delay (ms)
      - spinbox R: 0–255
      - spinbox G: 0–255
      - spinbox B: 0–255
    """

    def __init__(self, action_data, parent=None):
        super().__init__(action_data, parent=parent)

    def _create_ui(self):
        layout = self.main_layout

        # --- Riga Device (side) ---
        row_side = QtWidgets.QHBoxLayout()
        row_side.addWidget(QtWidgets.QLabel("Device"))

        self.side_combo = QtWidgets.QComboBox()
        self.side_combo.addItems(["BOTH", "LEFT", "RIGHT"])
        self.side_combo.currentIndexChanged.connect(self._on_side_changed)
        row_side.addWidget(self.side_combo)

        row_side.addStretch()
        layout.addLayout(row_side)

        # --- Riga LED singolo ---
        row_led = QtWidgets.QHBoxLayout()
        row_led.addWidget(QtWidgets.QLabel("LED"))

        self.led_combo = QtWidgets.QComboBox()
        self.led_combo.addItems(LED_NAMES)
        self.led_combo.currentIndexChanged.connect(self._on_led_changed)
        row_led.addWidget(self.led_combo)

        row_led.addStretch()
        layout.addLayout(row_led)

        # --- Riga espressione multi-LED ---
        row_expr = QtWidgets.QHBoxLayout()
        row_expr.addWidget(QtWidgets.QLabel("LEDs Expr"))

        self.expr_edit = QtWidgets.QLineEdit()
        self.expr_edit.setPlaceholderText("es: LED1,LED2,LED3 oppure LED1/LED5")
        self.expr_edit.editingFinished.connect(self._on_expr_changed)
        row_expr.addWidget(self.expr_edit)

        row_expr.addStretch()
        layout.addLayout(row_expr)

        # --- Riga Invio (mode) ---
        row_mode = QtWidgets.QHBoxLayout()
        row_mode.addWidget(QtWidgets.QLabel("Invio"))

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["Tutti insieme", "Sequenziale (caterpillar)"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        row_mode.addWidget(self.mode_combo)

        row_mode.addStretch()
        layout.addLayout(row_mode)

        # --- Riga Effect ---
        row_eff = QtWidgets.QHBoxLayout()
        row_eff.addWidget(QtWidgets.QLabel("Effect"))

        self.effect_combo = QtWidgets.QComboBox()
        self.effect_combo.addItems(["Static", "Blink", "Fade", "Rainbow"])
        self.effect_combo.currentIndexChanged.connect(self._on_effect_changed)
        row_eff.addWidget(self.effect_combo)

        row_eff.addStretch()
        layout.addLayout(row_eff)

        # --- Riga Delay (ms) ---
        row_delay = QtWidgets.QHBoxLayout()
        row_delay.addWidget(QtWidgets.QLabel("Delay (ms)"))

        self.delay_spin = QtWidgets.QSpinBox()
        self.delay_spin.setRange(0, 60000)
        self.delay_spin.setSingleStep(50)
        self.delay_spin.valueChanged.connect(self._on_delay_changed)
        row_delay.addWidget(self.delay_spin)

        row_delay.addStretch()
        layout.addLayout(row_delay)

        # --- Riga R ---
        row_r = QtWidgets.QHBoxLayout()
        row_r.addWidget(QtWidgets.QLabel("R"))

        self.r_spin = QtWidgets.QSpinBox()
        self.r_spin.setRange(0, 255)
        self.r_spin.setSingleStep(1)
        self.r_spin.valueChanged.connect(self._on_r_changed)
        row_r.addWidget(self.r_spin)

        row_r.addStretch()
        layout.addLayout(row_r)

        # --- Riga G ---
        row_g = QtWidgets.QHBoxLayout()
        row_g.addWidget(QtWidgets.QLabel("G"))

        self.g_spin = QtWidgets.QSpinBox()
        self.g_spin.setRange(0, 255)
        self.g_spin.setSingleStep(1)
        self.g_spin.valueChanged.connect(self._on_g_changed)
        row_g.addWidget(self.g_spin)

        row_g.addStretch()
        layout.addLayout(row_g)

        # --- Riga B ---
        row_b = QtWidgets.QHBoxLayout()
        row_b.addWidget(QtWidgets.QLabel("B"))

        self.b_spin = QtWidgets.QSpinBox()
        self.b_spin.setRange(0, 255)
        self.b_spin.setSingleStep(1)
        self.b_spin.valueChanged.connect(self._on_b_changed)
        row_b.addWidget(self.b_spin)

        row_b.addStretch()
        layout.addLayout(row_b)

        layout.setContentsMargins(0, 0, 0, 0)

    def _populate_ui(self):
        """Carica i valori correnti dell'azione nella UI."""

        # side
        side = getattr(self.action_data, "led_side", "BOTH")
        side = (side or "BOTH").upper()
        idx_side = {"BOTH": 0, "LEFT": 1, "RIGHT": 2}.get(side, 0)
        self.side_combo.setCurrentIndex(idx_side)

        # led singolo
        led_name = getattr(self.action_data, "led_name", "LED1")
        try:
            idx_led = LED_NAMES.index(led_name)
        except ValueError:
            idx_led = 0
        self.led_combo.setCurrentIndex(idx_led)

        # espressione
        expr = getattr(self.action_data, "leds_expr", "")
        self.expr_edit.setText(expr)

        # mode
        mode = getattr(self.action_data, "sequence_mode", "BATCH").upper()
        idx_mode = {"BATCH": 0, "SEQ": 1}.get(mode, 0)
        self.mode_combo.setCurrentIndex(idx_mode)

        # effetto
        eff = getattr(self.action_data, "effect_mode", "STATIC").upper()
        idx_eff = {"STATIC": 0, "BLINK": 1, "FADE": 2, "RAINBOW": 3}.get(eff, 0)
        self.effect_combo.setCurrentIndex(idx_eff)

        # delay (ms)
        delay = int(getattr(self.action_data, "effect_delay_ms", 0))
        self.delay_spin.setValue(delay)

        # R / G / B
        self.r_spin.setValue(int(getattr(self.action_data, "color_r", 255)))
        self.g_spin.setValue(int(getattr(self.action_data, "color_g", 0)))
        self.b_spin.setValue(int(getattr(self.action_data, "color_b", 0)))

    def _on_side_changed(self, index: int):
        value = self.side_combo.currentText() or "BOTH"
        self.action_data.led_side = value.upper()
        self.action_modified.emit()

    def _on_led_changed(self, index: int):
        if 0 <= index < len(LED_NAMES):
            self.action_data.led_name = LED_NAMES[index]
        else:
            self.action_data.led_name = "LED1"
        self.action_modified.emit()

    def _on_expr_changed(self):
        text = self.expr_edit.text().strip()
        self.action_data.leds_expr = text
        self.action_modified.emit()

    def _on_mode_changed(self, index: int):
        # 0 = BATCH (tutti insieme), 1 = SEQ (caterpillar)
        self.action_data.sequence_mode = "SEQ" if index == 1 else "BATCH"
        self.action_modified.emit()

    def _on_effect_changed(self, index: int):
        # Mappa indice -> STATIC/BLINK/FADE/RAINBOW
        if index == 1:
            eff = "BLINK"
        elif index == 2:
            eff = "FADE"
        elif index == 3:
            eff = "RAINBOW"
        else:
            eff = "STATIC"
        self.action_data.effect_mode = eff
        self.action_modified.emit()

    def _on_delay_changed(self, value: int):
        self.action_data.effect_delay_ms = int(value)
        self.action_modified.emit()

    def _on_r_changed(self, value: int):
        self.action_data.color_r = int(value)
        self.action_modified.emit()

    def _on_g_changed(self, value: int):
        self.action_data.color_g = int(value)
        self.action_modified.emit()

    def _on_b_changed(self, value: int):
        self.action_data.color_b = int(value)
        self.action_modified.emit()


# ---------------------------------------------------------------------------
# Functor: invio TCP per uno o più LED con effetto
# ---------------------------------------------------------------------------

class LedsBaseFunctor(AbstractFunctor):
    """
    Quando l'azione si attiva:
      - espande l'espressione LEDs Expr (se presente),
      - oppure usa solo led_name,
      - e invia i comandi secondo la modalità:
        * BATCH: un'unica connessione con più righe (tutti insieme)
        * SEQ:   una connessione per LED (caterpillar) con eventuale delay
    """

    def __init__(self, action):
        super().__init__(action)
        self.action = action

    def process_event(self, event, value):
        try:
            etype = event.event_type
        except AttributeError:
            etype = None

        led_side = getattr(self.action, "led_side", "BOTH")
        base_led = getattr(self.action, "led_name", "LED1")
        expr = getattr(self.action, "leds_expr", "")

        r = int(getattr(self.action, "color_r", 255))
        g = int(getattr(self.action, "color_g", 0))
        b = int(getattr(self.action, "color_b", 0))

        effect = getattr(self.action, "effect_mode", "STATIC").upper()
        delay_ms = int(getattr(self.action, "effect_delay_ms", 0))

        leds = _expand_leds_expr(expr, base_led)
        mode = getattr(self.action, "sequence_mode", "BATCH").upper()
        sequential = (mode == "SEQ")

        log.info(
            f"[LEDs base] event={etype} side={led_side} leds={leds} "
            f"rgb=({r},{g},{b}) effect={effect} delay={delay_ms}ms "
            f"mode={'SEQ' if sequential else 'BATCH'} "
            f"pressed={getattr(event, 'is_pressed', None)}"
        )

        if not leds:
            return False

        # Per pulsanti / tastiera: solo on-press
        if etype in [InputType.JoystickButton, InputType.Keyboard]:
            if getattr(event, "is_pressed", False):
                if sequential:
                    for i, led_name in enumerate(leds):
                        _send_led(led_side, led_name, r, g, b, effect, delay_ms)
                        if i < len(leds) - 1 and delay_ms > 0:
                            time.sleep(delay_ms / 1000.0)
                else:
                    _send_leds_batch(led_side, leds, r, g, b, effect, delay_ms)
        else:
            # Altri tipi (asse / hat): invia sempre
            if sequential:
                for i, led_name in enumerate(leds):
                    _send_led(led_side, led_name, r, g, b, effect, delay_ms)
                    if i < len(leds) - 1 and delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)
            else:
                _send_leds_batch(led_side, leds, r, g, b, effect, delay_ms)

        return True


# ---------------------------------------------------------------------------
# Azione: struttura "pulita" con salvataggio XML
# ---------------------------------------------------------------------------

class LedsBase(AbstractAction):
    """Azione con:
        - led_side (BOTH/LEFT/RIGHT)
        - led_name (LED1, LED2, ..., LED10, LED11)
        - leds_expr (es. "LED1,LED2" o "LED1/LED5")
        - sequence_mode: BATCH / SEQ
        - effect_mode: STATIC / BLINK / FADE / RAINBOW
        - effect_delay_ms: delay / periodo in millisecondi
        - color_r (0–255)
        - color_g (0–255)
        - color_b (0–255)
    """

    name = "Leds Base RG"
    tag = "leds-base-rg"

    default_button_activation = (True, True)
    input_types = [
        InputType.JoystickAxis,
        InputType.JoystickButton,
        InputType.JoystickHat,
        InputType.Keyboard,
    ]

    functor = LedsBaseFunctor
    widget = LedsBaseWidget

    def __init__(self, parent):
        super().__init__(parent)
        self.led_side = "BOTH"
        self.led_name = "LED1"
        self.leds_expr = ""      # vuoto = usa solo led_name
        self.sequence_mode = "BATCH"  # BATCH = tutti insieme, SEQ = caterpillar
        self.effect_mode = "STATIC"
        self.effect_delay_ms = 0
        self.color_r = 255
        self.color_g = 0
        self.color_b = 0

    def icon(self):
        return "{}/icon.png".format(os.path.dirname(os.path.realpath(__file__)))

    def requires_virtual_button(self):
        input_type = self.get_input_type()
        if input_type in [InputType.JoystickButton, InputType.Keyboard]:
            return False
        elif input_type == InputType.JoystickAxis:
            return True
        elif input_type == InputType.JoystickHat:
            return True

    # ---------- XML ----------

    def _parse_xml(self, node):
        """Carica i parametri da XML."""
        # side
        side = node.get("side", "BOTH")
        self.led_side = (side or "BOTH").upper()

        # led singolo
        led = node.get("led", "LED1")
        self.led_name = led if led in LED_NAMES else "LED1"

        # espressione
        self.leds_expr = node.get("expr", "")

        # sequence mode
        mode = (node.get("mode", "BATCH") or "BATCH").upper()
        if mode not in ("BATCH", "SEQ"):
            mode = "BATCH"
        self.sequence_mode = mode

        # effect
        eff = node.get("effect", "STATIC").upper()
        if eff not in EFFECT_CHOICES:
            eff = "STATIC"
        self.effect_mode = eff

        # delay
        try:
            self.effect_delay_ms = int(node.get("delay", 0))
        except (TypeError, ValueError):
            self.effect_delay_ms = 0

        # r
        try:
            self.color_r = int(node.get("r", 255))
        except (TypeError, ValueError):
            self.color_r = 255

        # g
        try:
            self.color_g = int(node.get("g", 0))
        except (TypeError, ValueError):
            self.color_g = 0

        # b
        try:
            self.color_b = int(node.get("b", 0))
        except (TypeError, ValueError):
            self.color_b = 0

    def _generate_xml(self):
        """Salva i parametri in XML."""
        node = ElementTree.Element("leds-base-rg")
        node.set("side", self.led_side)
        node.set("led", self.led_name)
        node.set("expr", self.leds_expr or "")
        node.set("mode", self.sequence_mode or "BATCH")
        node.set("effect", self.effect_mode or "STATIC")
        node.set("delay", str(int(self.effect_delay_ms)))
        node.set("r", str(int(self.color_r)))
        node.set("g", str(int(self.color_g)))
        node.set("b", str(int(self.color_b)))
        return node

    def _is_valid(self):
        return bool(self.led_name)


# Metadati del plugin
version = 1
name = "leds-base-rg"
create = LedsBase
