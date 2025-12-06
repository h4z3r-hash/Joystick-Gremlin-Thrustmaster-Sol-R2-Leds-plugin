# SOLR2 LED Server + Joystick Gremlin Plugins

This project enables full LED control of **Thrustmaster SOL-R 2** devices (LEFT and RIGHT) via:

- a lightweight **Python LED USB Server** (`server.py`)
- **Joystick Gremlin plugins**:
  - `plugin.py` → automatically starts/stops the LED server when Gremlin is running
  - `__init__.py` → adds the **Leds Base RG** action with:
    - Multi-LED control  
    - LED grouping (LED9, LED10…)  
    - Device side selection: LEFT / RIGHT / BOTH  
    - Effects: `STATIC`, `BLINK`, `FADE`, `RAINBOW`  
    - Batch or sequential LED updates  
    - LED expressions (`LED1/LED5`, `LED1,LED3,LED7`)  
    - Custom icon (`icon.png`)

---

## ⚠️ DISCLAIMER

- This project is **not supported by Thrustmaster**.  
- You must replace the official **tmhbulk** USB driver with **libusbK** on VENDOR Interface 1.  
- Proceed only if you understand USB drivers and Joystick Gremlin configuration.  
- Use at your own risk.

---

# 1. Requirements

## Hardware

- Two **Thrustmaster SOL-R 2** devices (LEFT and RIGHT)
- Windows 10 / 11
- Optional but recommended: **HidHide**

## Software

- **Joystick Gremlin**  
- **vJoy**  
- **HidHide**  Optional
- **Python 3.10+**  
- **Zadig** (libusbk) driver (replaces Thrustmaster `tmhbulk` on VENDOR Interface 1)  

---

# 2. Installing Python

Use **CMD or PowerShell**:

```cmd
winget install Python.Python.3.10
python --version

You should see something like:

Python 3.10.x

Install required Python modules:
pip install pyusb


3. Driver Setup (Critical Step)

The LED server can only communicate with SOL-R 2 units if the VENDOR interface driver is replaced with libusbK.
Before doing this, you must prevent Windows from restoring the original Thrustmaster driver.

🔧 Step 1 — Disable Thrustmaster Services (Mandatory)

These services can automatically reinstall the tmhbulk driver if active.

Open the Windows services panel:

Win + R → services.msc → Enter


Look for these services (if present):

Thrustmaster FAST Service

Thrustmaster HOTAS Service

For each service:

Right-click → Properties

Set Startup type → Disabled

Click Stop

Click Apply

Important

These services may not appear if:

You never installed the official Thrustmaster T.A.R.G.E.T software, or

Your system only uses auto-installed Microsoft Store drivers.

If the services are missing, just continue to the next step.

🔧 Step 2 — If Zadig cannot modify the driver

Sometimes Zadig fails to install libusbK because Driver Signature Enforcement is enabled on Windows.

If Zadig shows errors such as:

“Driver installation failed”

“libusbK cannot be installed”

then temporarily disable driver signature enforcement.

Temporarily disable Driver Signature Enforcement

Press Shift + Restart in Windows

Navigate:

Troubleshoot → Advanced Options → Startup Settings


Press 7 → Disable driver signature enforcement

Windows will reboot in a mode that allows unsigned driver installation

Run Zadig again and install libusbK

After that, you can reboot normally and Windows will return to standard mode

🔧 Step 3 — Replace tmhbulk with libusbK using Zadig

Open Zadig

Go to: Options → List All Devices

Identify the correct interfaces: "DO NOT SELECT SOL R FLIGHTSTICK INTERFACE 0!"

VENDOR – Interface 1 

VENDOR – Interface 1

Only Interface 1 is the vendor channel used for LEDs.

For each of those interfaces:

In the driver selection box:

From → Thrustmaster tmhbulk

To → libusbK

Click Install Driver

After both are done, unplug and reconnect both SOL-R 2 devices.

⚠️ IMPORTANT

Do NOT modify HID interfaces

LEDs will work only if Interface 1 uses libusbK on both devices

4. Installing the Plugins

Copy the files to the appropriate Joystick Gremlin folders.

File	Location
server.py	C:\Program Files (x86)\H2ik\Joystick Gremlin\Plugins\
plugin.py	C:\Program Files (x86)\H2ik\Joystick Gremlin\Plugins\
__init__.py	C:\Program Files (x86)\H2ik\Joystick Gremlin\action_plugins\leds\
icon.png	C:\Program Files (x86)\H2ik\Joystick Gremlin\action_plugins\leds\

The leds folder inside action_plugins should contain at least:

__init__.py

icon.png

5. Adding the Plugin in Joystick Gremlin

Launch Joystick Gremlin

Go to the Plugins tab

Click Add Plugin

Browse to and select plugin.py

Save your Gremlin profile

From now on:

When the profile is Running and Active, plugin.py will auto-start server.py

When the profile stops / Gremlin exits, the server is stopped

6. Using the “Leds Base RG” Action

When Gremlin is not running:

Press a button on one of your SOL-R 2 devices

The right-side editor pane will open

In the action dropdown, select Leds Base RG

Action features

Device selection: BOTH, LEFT, RIGHT

Single LED selection: LED1…LED11, LED9A…LED9H, LED10A…LED10C

LEDs Expr (LED expression):

If empty → affects only the selected single LED

If not empty → overrides the LED list

LED expressions

You can specify:

Ranges using /:

LED1/LED5        → LED1, LED2, LED3, LED4, LED5


Lists using ,:

LED1,LED3,LED7


Group aliases:

LED9 → expands to LED9A … LED9H

LED10 → expands to LED10A … LED10C

Send mode

All at once

Sequential (caterpillar) → sends one LED at a time, with optional delay

Effects

The action supports the following effects:

STATIC

BLINK

FADE

RAINBOW

The Delay (ms) parameter is used as:

Blink → ON/OFF half-period

Fade → full fade-in/fade-out period

Rainbow → full color cycle period

7. vJoy Configuration

This setup expects two vJoy devices to be configured in vJoy Configurator.

⚠️ VERY IMPORTANT

vJoy1 and vJoy2 must NOT have the same number of buttons.
If both vJoy devices have identical configurations, Joystick Gremlin may fail to distinguish them properly and mappings may not work reliably.

Example configuration:

vJoy Device 1:

32 buttons

vJoy Device 2:

64 buttons

Configure vJoy according to the screenshots:

docs/vjoy1.png

docs/vjoy2.png

Make sure to:

Enable only the axes you actually need

Give each vJoy device a different button count

Apply/save configuration in vJoy before running Gremlin

8. HidHide Configuration

Use HidHide so that games only see the virtual vJoy devices and not the physical devices directly.

Screenshot reference:

docs/hidhide.png

Recommended configuration

In the Devices tab:

Enable hiding for:

SOL-R 2 LEFT

SOL-R 2 RIGHT

Any physical HOTAS / joystick you want hidden from games

In the Applications tab:

Add:

JoystickGremlin.exe

Any other config tools you want to have access to the real devices

Make sure game executables are NOT added:

Games should see only the vJoy devices, not the physical ones.

9. Running the LED Server Manually (Debug Mode)

Normally, plugin.py will start server.py automatically.

If you want to run the server manually for debugging:

Remove / disable plugin.py in the Gremlin Plugins tab
(to avoid having two servers at the same time)

Run this command in CMD or PowerShell:

python "C:\Program Files (x86)\H2ik\Joystick Gremlin\Plugins\server.py" --debug --tx-delay-ms 0 --repeat 0 --max-entries 4 --stream-interval-ms 1


This will:

Print all received commands

Show internal LED state updates

Dump USB payloads

Display transitions for BLINK / FADE / RAINBOW effects

Show any errors/exceptions

Very useful for development and support.



11. Contributions

Contributions are welcome, including:

Improving LED mapping and color handling

Optimizing USB performance / packet batching

Enhancing effects (e.g., per-LED phase shifts, wave patterns, etc.)

Improving error handling and logging

Extending documentation and examples

Feel free to open issues or pull requests if you want to help evolve this project.
