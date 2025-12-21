SOLR2 LED Server + Joystick Gremlin Plugins
==========================================

This project enables full LED control of Thrustmaster SOL-R 2 devices (LEFT and RIGHT) via:

- a lightweight Python LED USB Server (server.py)
- Joystick Gremlin plugins:
  • plugin.py → automatically starts/stops the LED server when Gremlin is running
  • __init__.py → adds the “Leds Base RG” action with:
      - Multi-LED control
      - LED grouping (LED9, LED10…)
      - Device side selection: LEFT / RIGHT / BOTH
      - Effects: STATIC, BLINK, FADE, RAINBOW
      - Batch or sequential LED updates
      - LED expressions (LED1/LED5, LED1,LED3,LED7)
      - Custom icon (icon.png)

-------------------------------------------------------------------------------
⚠️ DISCLAIMER
-------------------------------------------------------------------------------

- This project is NOT supported by Thrustmaster.
- You MUST replace the Thrustmaster tmhbulk USB driver with libusbK on VENDOR Interface 1.
- Proceed only if you understand USB drivers and Joystick Gremlin configuration.
- Use at your own risk.

-------------------------------------------------------------------------------
1. REQUIREMENTS
-------------------------------------------------------------------------------

Hardware:
- 2x Thrustmaster SOL-R 2 (LEFT & RIGHT)
- Windows 10/11

Software:
- Joystick Gremlin
- vJoy
- HidHide (optional)
- Python 3.10+
- Zadig (to install libusbK driver)
  
-------------------------------------------------------------------------------
2. INSTALLING PYTHON
-------------------------------------------------------------------------------

Run in CMD or PowerShell:

    winget install Python.Python.3.10 (on win 11 add " --source winget")
    python --version

Expected:

    Python 3.10.x

Install the required module:

    pip install pyusb

-------------------------------------------------------------------------------
3. DRIVER SETUP (CRITICAL STEP)
-------------------------------------------------------------------------------

The LED server ONLY works if SOL-R 2 “VENDOR – Interface 1” uses libusbK.

Before modifying drivers, prevent Windows from restoring original ones.

--------------------------
Step 1 — Disable Thrustmaster Services
--------------------------

Open Windows Services:

    Win + R → services.msc → Enter

Disable these services IF they exist:

- Thrustmaster FAST Service
- Thrustmaster HOTAS Service

If services do not appear:
→ You likely never installed Thrustmaster T.A.R.G.E.T, continue normally.

--------------------------
Step 2 — If Zadig Cannot Modify Driver
--------------------------

If Zadig shows errors like:
- "Driver installation failed"
- "libusbK cannot be installed"

Disable Driver Signature Enforcement temporarily:

1. Shift + Restart
2. Navigate: Troubleshoot → Advanced Options → Startup Settings
3. Press 7 = Disable driver signature enforcement
4. Install libusbK through Zadig
5. Reboot normally afterward

--------------------------
Step 3 — Replace tmhbulk with libusbK using Zadig
--------------------------

1. Open Zadig
2. Select: Options → List All Devices
3. Locate ONLY:

    VENDOR – Interface 1 (RIGHT)
    VENDOR – Interface 1 (LEFT)

⚠️ DO NOT SELECT:
“SOL R FLIGHTSTICK – Interface 0”  
DO NOT MODIFY HID interfaces.

4. Set driver:
   From → tmhbulk  
   To   → libusbK

5. Install Driver
6. Unplug and reconnect both SOL-R 2 devices


4. VJOY CONFIGURATION
-------------------------------------------------------------------------------

Two vJoy devices MUST be created.

⚠️ CRITICAL RULE:
vJoy1 and vJoy2 MUST NOT have the same number of buttons.

Example working setup:

vJoy Device 1:
    128 buttons

vJoy Device 2:
    127 buttons

See images:
    docs/vjoy1.png
    docs/vjoy2.png

Ensure:
- Different button counts
- Only needed axes enabled
- Save configuration before launching Gremlin
-------------------------------------------------------------------------------
5. INSTALLING THE PLUGINS
-------------------------------------------------------------------------------

Copy files:

"\Plugins\server.py"  → C:\Program Files (x86)\H2ik\Joystick Gremlin\Plugins\
"\Plugins\plugin.py"  → C:\Program Files (x86)\H2ik\Joystick Gremlin\Plugins\
"\leds\__init__.py" + icon.png → C:\Program Files (x86)\H2ik\Joystick Gremlin\action_plugins\leds\

Folders structure:

Plugins
    ├── server.py
    └── plugin.py
action_plugins\leds\
    ├── __init__.py
    └── icon.png

-------------------------------------------------------------------------------
6. ADDING THE PLUGIN IN JOYSTICK GREMLIN
-------------------------------------------------------------------------------

1. Open Joystick Gremlin
2. Go to Plugins tab
3. Add Plugin
4. Select plugin.py
5. Save profile

Behavior:
- When Gremlin is Running and Active → server starts
- When Gremlin stops → server stops

-------------------------------------------------------------------------------
7. USING THE “Leds Base RG” ACTION
-------------------------------------------------------------------------------

Steps:
1. Stop Gremlin
2. Press a SOL-R button
3. In the action list select "Leds Base RG"

Features:
- Device: LEFT / RIGHT / BOTH
- LED selection: LED1…LED11, LED9A-H, LED10A-C
- LEDs Expr (range or list)

LED Ranges:

    LED1/LED5  → LED1,LED2,LED3,LED4,LED5

Lists:

    LED1,LED3,LED7

Groups:

    LED9  → LED9A..LED9H
    LED10 → LED10A..LED10C

Effects:
STATIC, BLINK, FADE, RAINBOW

Send Modes:
- All at once
- Sequential (caterpillar)

Delay Meaning:
- Blink  = ON/OFF half-cycle
- Fade   = Fade-in/out cycle
- Rainbow = Full color cycle speed

-------------------------------------------------------------------------------
-------------------------------------------------------------------------------
8. HIDHIDE CONFIGURATION
-------------------------------------------------------------------------------

Use HidHide to hide physical devices from games.

See image:
    docs/hidhide.png

Recommended settings:

Devices tab:
- Hide SOL-R 2 LEFT
- Hide SOL-R 2 RIGHT
- Hide physical HOTAS devices

Applications tab:
- Allow JoystickGremlin.exe
- Allow other tools (NOT games)

Games must NOT appear here → they must only see vJoy.

-------------------------------------------------------------------------------
9. RUNNING THE LED SERVER MANUALLY (DEBUG MODE)
-------------------------------------------------------------------------------

Disable plugin.py in Gremlin first to avoid two servers running.

Run manually:

    python "C:\Program Files (x86)\H2ik\Joystick Gremlin\Plugins\server.py" --debug --tx-delay-ms 0 --repeat 0 --max-entries 4 --stream-interval-ms 1

Debug mode displays:
- LED commands received
- Internal state transitions
- USB packets
- Effect behavior
- Errors/exceptions

-------------------------------------------------------------------------------
10. CONTRIBUTIONS
-------------------------------------------------------------------------------

Contributions are welcome:
- LED mapping improvements
- Additional effects
- USB optimization
- Logging enhancements
- Documentation

Open issues or pull requests to support development.

