# SOLR2 LED Server + Joystick Gremlin Plugins

Questo progetto permette di controllare i LED dei due **Thrustmaster SOL-R 2** tramite:

- un piccolo **server Python** (`server.py`) che parla con le periferiche via USB (libusbK)
- uno o più **plugin per Joystick Gremlin**:
  - `plugin.py` → avvia/ferma automaticamente il server
  - `__init__.py` → azione **Leds Base RG** con effetti: `STATIC`, `BLINK`, `FADE`, `RAINBOW`, multi-LED, side LEFT/RIGHT/BOTH, ecc.

> ⚠️ **ATTENZIONE / DISCLAIMER**
>
> - Questa configurazione non è ufficialmente supportata da Thrustmaster.
> - Vengono sostituiti i driver originali (tmhbulk) con **libusbK** sulle interfacce VENDOR dei SOL-R 2.
> - Tutto è a tuo rischio: esegui il setup solo se sai cosa stai facendo e hai dimestichezza con driver e dispositivi USB.


---

## 1. Requisiti

### Hardware

- 2x **Thrustmaster SOL-R 2** (LEFT / RIGHT)
- PC Windows 10 / 11
- Eventuale HOTAS / joystick configurato tramite vJoy + HidHide

### Software

- **Joystick Gremlin** (necessario, il progetto funziona come plugin)
- **vJoy** (driver di joystick virtuale)
- **HidHide** (per nascondere le periferiche fisiche ai giochi)
- **Python 3.10+** (consigliato) installato su Windows
- **Driver libusbK** per le interfacce VENDOR dei SOL-R 2

### Python – librerie necessarie

Sul PC dove userai il server:

```bash
pip install pyusb
