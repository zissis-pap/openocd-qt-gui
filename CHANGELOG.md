# Changelog

All notable changes to this project will be documented in this file.

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
