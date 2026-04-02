# Changelog

All notable changes to this project will be documented in this file.

## [0.032] - 2026-04-02
### Added
- **Variable counter column** — a read-only `#` column to the left of Address auto-numbers each row; updated on add/remove
- **Data format selector** — `QComboBox` (Hex / Decimal / ASCII) above the variable table; switching reformats all Data cells without losing values
- **Current Value format selector** — matching `QComboBox`; switching reformats existing Current Value cells using stored raw bytes without re-reading flash
- **Auto-read on Load Set** — loading a `.varset` file now automatically triggers a flash read so Current Value is populated immediately

## [0.031] - 2026-04-02
### Added
- **Data column auto-formatting** — Data (hex) field is automatically reformatted to a
  zero-padded hex string matching the variable's byte width whenever Size or Data is
  edited (e.g. size=4 → `0xDEADBEEF`); same reformatting applies after Load Set
- **Consistent Current Value format** — Current Value now always displays as a
  zero-padded hex integer matching the variable width (little-endian unsigned), plus
  quoted ASCII when printable; for variables >4 bytes the ASCII string is shown, falling
  back to a space-separated hex dump

### Fixed
- **Content Editor Store** — replaced separate `flash erase_address` + `flash write_image`
  with the atomic `flash write_image erase` command; added response error checking and
  a read-size guard to detect truncated sector reads before writing

## [0.030] - 2026-04-02
### Changed
- **Content Editor layout** — the Variables table and Store panel are now separated by
  a vertical splitter; drag the handle to resize either section; the table expands with
  the window while the store panel stays compact; neither panel can be collapsed to zero

## [0.029] - 2026-04-02
### Added
- **Stop external OpenOCD** — when an already-running OpenOCD instance is detected at
  startup, the Stop button is now enabled; clicking it sends a `shutdown` command via
  the telnet interface (using the live connection if already connected, or a temporary
  one otherwise) and resets the UI to the Stopped state on success
- **Disconnect from externally-detected instance** — the Disconnect button remains
  available after connecting to an external instance, allowing the telnet session to
  be closed without stopping the OpenOCD process

## [0.028] - 2026-04-02
### Added
- **Startup OpenOCD detection** — on launch the app probes the configured telnet port
  (default 4444); if an already-running OpenOCD instance is found, the status dot turns
  amber ("Running externally"), the Connect button is enabled automatically, and an
  informational message is shown in the log panel and status bar

### Fixed
- **Worker lifecycle crash on repeated reads** — `MemReadWorker` and `FlashInfoWorker`
  now use `deleteLater` for Qt-safe cleanup; previously, Python's GC could destroy a
  `QThread` object before Qt finished its internal teardown, causing a crash on the
  second whole-flash read

## [0.027] - 2026-04-02
### Added
- **Memory Viewer progress bar** — a progress bar appears below the controls while
  a memory read is in progress and hides automatically when the table is populated
  or on error; progress is updated per 64-word chunk so large reads (e.g. whole flash
  on high-density MCUs) show smooth incremental feedback

## [0.026] - 2026-04-02
### Added
- **Read Whole Flash in Memory Viewer** — new "Read Whole Flash" button queries
  `flash info 0` to discover the flash bank base address and total size (sum of all
  sectors), populates the address and size fields automatically, and triggers a full
  read; the detected geometry is reported in the log panel

## [0.025] - 2026-04-02
### Added
- **Current Value column in Content Editor** — reads the value currently stored in flash
  for each variable and displays it in the table; values ≤ 65535 are shown in decimal,
  larger values in hex; for variables > 4 bytes (e.g. strings) the ASCII representation
  is shown instead of a numeric value, with `.` substituted for non-printable bytes;
  non-printable-only buffers fall back to a space-separated hex dump
- **Read Values button** — manually triggers a flash read for all defined variables;
  current values are also refreshed automatically after a successful Store operation

## [0.024] - 2026-04-02
### Added
- **Content Editor tab** — new tab for read-modify-erase-write of named flash variables;
  each variable has an address, name, size (bytes), and data (hex); the **Store** button
  reads all affected flash sectors, patches the variable bytes, erases, and writes back;
  multiple variables spanning multiple sectors are handled in a single operation
- **Save/Load variable set** — variable tables can be saved to `.varset`/`.json` files
  and reloaded across sessions

## [0.022] - 2026-02-17
### Added
- **Flash-aware byte write in Memory Viewer** — writes to flash addresses
  (`≥ 0x08000000`) now perform a full read-modify-erase-write cycle using
  `flash info 0` to locate the containing sector, reading back the sector,
  patching the single byte, erasing, and programming via a temporary `.bin`
  file; writes to RAM addresses still use the fast `mww` path
- **Verify tab** — new permanent tab showing a side-by-side comparison of
  flash contents vs a firmware binary file; each byte cell is colour-coded
  (green = match, amber = differ); a summary label above the table reports
  filename, base address, total bytes, match count, and differ count;
  clicking **Verify** in Flash Ops switches to this tab automatically

### Changed
- **Flash Ops → Verify button** — no longer runs `verify_image` directly;
  instead emits `sig_verify_requested` which triggers the Verify tab worker

## [0.021] - 2026-02-17
### Added
- Initial versioned release
- About dialog now displays the application version
- CHANGELOG and auto-versioning via pre-commit hook
- **Server control** — launch and terminate the OpenOCD subprocess from the GUI; live PID display and status indicator
- **MCU selector** — built-in tree covering all major STM32 families (F0/F1/F2/F3/F4/F7/H7/L0/L1/L4/L4+/L5/G0/G4/U5/WB/WL); custom `.cfg` file input also supported
- **Flash operations** — Halt, Erase, Program, Verify, Reset & Run, and Read (binary dump); progress bar for multi-step operations
- **Memory viewer** — live hex dump with 16-byte rows; inline write-back via `mww`; optional auto-refresh at configurable interval (≥ 500 ms); address and ASCII columns
- **Script console** — interactive TCL prompt with 100-command history (↑/↓ navigation) and colour-coded output; multi-line script editor with Load/Save/Run support
- **Live log panel** — real-time OpenOCD stdout/stderr; colour-coded entries; Clear and Save Log actions
- **Dark theme** — automatic via `qdarkstyle`; graceful fallback palette when not installed
- **Debug interface support** — ST-Link, ST-Link v2, ST-Link v2-1, J-Link, CMSIS-DAP, FTDI
