# OpenOCD Qt GUI

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt5](https://img.shields.io/badge/PyQt5-5.12%2B-41CD52?logo=qt&logoColor=white)](https://pypi.org/project/PyQt5/)
[![OpenOCD](https://img.shields.io/badge/OpenOCD-0.11%2B-FF6600?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PC9zdmc+&logoColor=white)](https://openocd.org/)
[![QDarkStyle](https://img.shields.io/badge/qdarkstyle-optional-555555)](https://github.com/ColinDuquesnoy/QDarkStyleSheet)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)](https://github.com/zissis-pap/openocd-qt-gui)
[![STM32](https://img.shields.io/badge/target-STM32-03234B?logo=stmicroelectronics&logoColor=white)](https://www.st.com/en/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus.html)
[![Version](https://img.shields.io/badge/version-0.022-informational)](CHANGELOG.md)

A **PyQt5 graphical frontend** for the [OpenOCD](https://openocd.org/) on-chip debugger.
It lets you start/stop the OpenOCD server, flash firmware, inspect memory, and run
TCL scripts — all without touching a terminal.

> OpenOCD must be installed on your system separately. This tool is a GUI wrapper only.

![](assets/launch_window.png)

---

## Features

| Feature | Description |
|---|---|
| **Server control** | Launch and terminate the OpenOCD subprocess from the GUI |
| **MCU selector** | Built-in tree for all major STM32 families; custom `.cfg` also supported |
| **Flash operations** | Halt · Erase · Program · Verify · Reset & Run · Read (dump) flash |
| **Memory viewer** | Live hex dump with inline write-back and optional auto-refresh |
| **Script console** | Interactive TCL prompt with command history + multi-line script editor |
| **Live log** | Scrollable, colour-coded output panel; exportable to file |
| **Dark theme** | Automatic via `qdarkstyle`; graceful fallback palette if not installed |

### Supported STM32 families

STM32F0, F1, F2, F3, F4, F7, H7, L0, L1, L4, L4+, L5, G0, G4, U5, WB, WL

### Supported debug interfaces

ST-Link, ST-Link v2, ST-Link v2-1, J-Link, CMSIS-DAP, FTDI

---

## Requirements

| Dependency | Version | Link |
|---|---|---|
| [Python](https://www.python.org/) | 3.8 + | https://www.python.org/downloads/ |
| [PyQt5](https://pypi.org/project/PyQt5/) | 5.12 + | https://pypi.org/project/PyQt5/ |
| [OpenOCD](https://openocd.org/) | 0.11 + (system package) | https://openocd.org/ |
| [qdarkstyle](https://github.com/ColinDuquesnoy/QDarkStyleSheet) *(optional)* | 3.x | https://github.com/ColinDuquesnoy/QDarkStyleSheet |

---

## Installation

### 1 — Install OpenOCD

**Debian / Ubuntu / Raspberry Pi OS**
```bash
sudo apt install openocd
```

**Arch Linux**
```bash
sudo pacman -S openocd
```

**Fedora**
```bash
sudo dnf install openocd
```

**macOS (Homebrew)**
```bash
brew install open-ocd
```

Verify the installation:
```bash
openocd --version
```

---

### 2 — Clone the repository

```bash
git clone https://github.com/zissis-pap/openocd-qt-gui.git
cd openocd-qt-gui
```

---

### 3 — Install Python dependencies

```bash
pip install PyQt5
pip install qdarkstyle        # optional but recommended
```

Or use a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install PyQt5 qdarkstyle
```

---

### 4 — Install the pre-commit hook (optional, for contributors)

After a fresh clone, copy the hook to activate auto-versioning on commit:

```bash
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

---

### 5 — Run

```bash
python main.py
```

---

## Usage walkthrough

### Step 1 — Configure the server (left panel)

| Field | Description |
|---|---|
| **Executable** | Path to `openocd`. If it is on your `PATH`, leave it as `openocd`. Use `...` to browse to a custom binary. |
| **Interface** | The debug adapter connected to your PC (e.g. `ST-Link`). |
| **Telnet port** | Port OpenOCD listens on for commands (default `4444`). |
| **TCL port** | Port for the TCL server (default `6666`). |

### Step 2 — Select the target MCU

Expand the **Target MCU** tree on the left and click the family or specific part number
(e.g. `STM32L4 → L412`).

The matching OpenOCD config path (`target/stm32l4x.cfg`) is shown below the tree and
is passed to the server automatically on start.

For a board not in the list, type or browse to a custom `.cfg` file in the
**Custom Config** box.

![](assets/select_mcu.png)

### Step 3 — Start the server

Click **Start**. The status dot turns green and the PID is shown.
OpenOCD output appears immediately in the **log panel** at the bottom.

### Step 4 — Connect

Click **Connect** to open a telnet session on the configured port.
The status bar changes from *Disconnected* (red) to *Connected* (green).
The Flash Ops, Memory Viewer, and Script Console tabs are now active.

![](assets/connected.png)

---

### Flash Ops tab

1. Click **Browse** (or use *File → Open Firmware…*) to select your firmware.
   Supported formats: `.bin`, `.elf`, `.hex`, `.s19`.
2. Set the **Base address** if needed (default `0x08000000` for STM32).
3. Use the operation buttons:

| Button | What it does |
|---|---|
| **Halt** | Halts the CPU (`halt`) |
| **Erase** | Halts then erases flash from the base address |
| **Program** | Halts then programs and verifies the selected file |
| **Verify** | Verifies the selected file against flash without writing |
| **Reset & Run** | Issues `reset run` to restart and execute firmware |
| **Read Flash** | Halts, prompts for a save path, then dumps flash to a `.bin` file |

A progress bar tracks multi-step operations. All output is forwarded to the log panel.

![](assets/app_launch.png)

---

### Memory Viewer tab

1. Enter a **hex or decimal address** (e.g. `0x20000000` for SRAM).
2. Enter the number of **bytes** to read (e.g. `256`).
3. Click **Read** (or **Refresh** to re-read the same region).

The table displays:
- **Address** column (blue) — start address of each row.
- **16 byte columns** — editable hex values. Changing a cell writes the enclosing
  32-bit word back to the target immediately using `mww`.
- **ASCII** column (green) — printable characters; `.` for non-printable bytes.

Enable **Auto-refresh** and set an interval (minimum 500 ms) to continuously poll
the memory region — useful for watching live register or variable values.

![](assets/memory_viewer.png)

---

### Script Console tab

#### Interactive console (top half)

- Type any OpenOCD/TCL command in the input field and press **Enter** or click **Send**.
- Use the **↑ / ↓ arrow keys** to navigate through the last 100 commands.
- Output is colour-coded: commands in blue, errors in red, normal output in light grey.

#### Script editor (bottom half)

- Write or paste a multi-line TCL script. Lines beginning with `#` are treated as
  comments and skipped.
- **Load Script** — open an existing `.tcl` file.
- **Save Script** — save the current editor content to a `.tcl` file.
- **Run Script** — execute all non-comment lines sequentially; output appears in the
  console above.

Example script (erase, flash, and run):
```tcl
# Full flash cycle
halt
flash erase_address pad 0x08000000 0x20000
program /path/to/firmware.bin 0x08000000 verify
reset run
```

![](assets/script_window.png)

---

### Log panel

The log panel at the bottom captures all output:

- OpenOCD stdout/stderr is streamed in real time.
- Responses to commands from Flash Ops, Memory Viewer, and Script Console are
  appended here as well.
- **Clear** removes all entries.
- **Save Log** exports the full log to a text file.

---

## Project structure

```
openocd-qt-gui/
├── main.py               Entry point; initialises the Qt application
├── mainwindow.py         Main window layout and signal wiring
├── openocd_manager.py    Subprocess lifecycle (start / stop / stdout capture)
├── openocd_client.py     Telnet client (async + synchronous variants)
├── mcu_config.py         STM32 family definitions and interface configs
└── widgets/
    ├── server_control.py  Server configuration and start/stop/connect buttons
    ├── mcu_selector.py    MCU family tree + custom config input
    ├── flash_ops.py       Flash operations tab
    ├── memory_viewer.py   Hex memory viewer/editor tab
    ├── script_console.py  Interactive TCL console + script editor tab
    └── log_widget.py      Scrollable log output panel
```

---

## Troubleshooting

**`OpenOCD executable not found`**
Ensure `openocd` is on your `PATH` (`which openocd`) or provide the full path in the
*Executable* field.

**`Cannot connect to OpenOCD at localhost:4444`**
The server must be fully started and listening before you click **Connect**. Watch the
log panel — OpenOCD prints `Listening on port 4444 for telnet connections` when ready.

**Permission denied on the debug adapter (Linux)**
Add a udev rule for your adapter, e.g. for ST-Link:
```bash
sudo cp /usr/share/openocd/contrib/60-openocd.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```
Then re-plug the adapter and add your user to the `plugdev` group:
```bash
sudo usermod -aG plugdev $USER
```

**Communication errors / polling failures in the log**
These are usually OpenOCD polling the target while it is running. They are harmless and
will stop once you click **Halt**.

---

## License

This project is licensed under the **GNU General Public License v3.0**.
See the [LICENSE](LICENSE) file for the full text.
