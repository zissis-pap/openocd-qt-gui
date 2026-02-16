"""STM32 family configurations for OpenOCD target selection."""

STM32_FAMILIES = {
    "STM32F0": {
        "target_config": "target/stm32f0x.cfg",
        "description": "STM32F0 - Cortex-M0 entry-level",
        "flash_size_hint": 256 * 1024,
        "series": ["F030", "F031", "F038", "F042", "F048", "F051", "F058",
                   "F070", "F071", "F072", "F078", "F091", "F098"],
    },
    "STM32F1": {
        "target_config": "target/stm32f1x.cfg",
        "description": "STM32F1 - Cortex-M3 mainstream",
        "flash_size_hint": 512 * 1024,
        "series": ["F100", "F101", "F102", "F103", "F105", "F107"],
    },
    "STM32F2": {
        "target_config": "target/stm32f2x.cfg",
        "description": "STM32F2 - Cortex-M3 high performance",
        "flash_size_hint": 1024 * 1024,
        "series": ["F205", "F207", "F215", "F217"],
    },
    "STM32F3": {
        "target_config": "target/stm32f3x.cfg",
        "description": "STM32F3 - Cortex-M4 mixed-signal",
        "flash_size_hint": 512 * 1024,
        "series": ["F301", "F302", "F303", "F313", "F318", "F328", "F334",
                   "F358", "F373", "F378", "F398"],
    },
    "STM32F4": {
        "target_config": "target/stm32f4x.cfg",
        "description": "STM32F4 - Cortex-M4 high performance",
        "flash_size_hint": 2048 * 1024,
        "series": ["F401", "F405", "F407", "F410", "F411", "F412", "F413",
                   "F415", "F417", "F423", "F427", "F429", "F437", "F439",
                   "F446", "F469", "F479"],
    },
    "STM32F7": {
        "target_config": "target/stm32f7x.cfg",
        "description": "STM32F7 - Cortex-M7 high performance",
        "flash_size_hint": 2048 * 1024,
        "series": ["F722", "F723", "F730", "F732", "F733", "F745", "F746",
                   "F750", "F756", "F765", "F767", "F769", "F777", "F779"],
    },
    "STM32H7": {
        "target_config": "target/stm32h7x.cfg",
        "description": "STM32H7 - Cortex-M7 ultra high performance",
        "flash_size_hint": 2048 * 1024,
        "series": ["H723", "H725", "H730", "H733", "H735", "H742", "H743",
                   "H745", "H747", "H750", "H753", "H755", "H757"],
    },
    "STM32L0": {
        "target_config": "target/stm32l0.cfg",
        "description": "STM32L0 - Cortex-M0+ ultra low power",
        "flash_size_hint": 192 * 1024,
        "series": ["L010", "L011", "L021", "L031", "L041", "L051", "L052",
                   "L053", "L062", "L063", "L071", "L072", "L073", "L081",
                   "L082", "L083"],
    },
    "STM32L1": {
        "target_config": "target/stm32l1.cfg",
        "description": "STM32L1 - Cortex-M3 ultra low power",
        "flash_size_hint": 512 * 1024,
        "series": ["L100", "L151", "L152", "L162"],
    },
    "STM32L4": {
        "target_config": "target/stm32l4x.cfg",
        "description": "STM32L4 - Cortex-M4 ultra low power",
        "flash_size_hint": 1024 * 1024,
        "series": ["L412", "L422", "L431", "L432", "L433", "L442", "L443",
                   "L451", "L452", "L462", "L471", "L475", "L476", "L485",
                   "L486", "L496", "L4A6"],
    },
    "STM32L4+": {
        "target_config": "target/stm32l4x.cfg",
        "description": "STM32L4+ - Cortex-M4 ultra low power plus",
        "flash_size_hint": 2048 * 1024,
        "series": ["L4P5", "L4Q5", "L4R5", "L4R7", "L4R9", "L4S5", "L4S7", "L4S9"],
    },
    "STM32L5": {
        "target_config": "target/stm32l5x.cfg",
        "description": "STM32L5 - Cortex-M33 ultra low power with TrustZone",
        "flash_size_hint": 512 * 1024,
        "series": ["L552", "L562"],
    },
    "STM32G0": {
        "target_config": "target/stm32g0x.cfg",
        "description": "STM32G0 - Cortex-M0+ mainstream",
        "flash_size_hint": 512 * 1024,
        "series": ["G030", "G031", "G041", "G050", "G051", "G061", "G070",
                   "G071", "G081", "G0B0", "G0B1", "G0C1"],
    },
    "STM32G4": {
        "target_config": "target/stm32g4x.cfg",
        "description": "STM32G4 - Cortex-M4 mixed-signal",
        "flash_size_hint": 512 * 1024,
        "series": ["G431", "G441", "G471", "G473", "G474", "G483", "G484",
                   "G491", "G4A1"],
    },
    "STM32U5": {
        "target_config": "target/stm32u5x.cfg",
        "description": "STM32U5 - Cortex-M33 ultra low power",
        "flash_size_hint": 4096 * 1024,
        "series": ["U535", "U545", "U575", "U585", "U595", "U5A5", "U5F7", "U5G7"],
    },
    "STM32WB": {
        "target_config": "target/stm32wbx.cfg",
        "description": "STM32WB - Cortex-M4/M0+ wireless",
        "flash_size_hint": 1024 * 1024,
        "series": ["WB10", "WB15", "WB30", "WB35", "WB50", "WB55", "WB5M"],
    },
    "STM32WL": {
        "target_config": "target/stm32wlx.cfg",
        "description": "STM32WL - Cortex-M4/M0+ sub-GHz wireless",
        "flash_size_hint": 256 * 1024,
        "series": ["WL54", "WL55", "WLE4", "WLE5"],
    },
}

INTERFACE_CONFIGS = {
    "ST-Link": "interface/stlink.cfg",
    "ST-Link v2": "interface/stlink-v2.cfg",
    "ST-Link v2-1": "interface/stlink-v2-1.cfg",
    "J-Link": "interface/jlink.cfg",
    "CMSIS-DAP": "interface/cmsis-dap.cfg",
    "FTDI": "interface/ftdi/um232h.cfg",
}

DEFAULT_INTERFACE = "ST-Link"
DEFAULT_TELNET_PORT = 4444
DEFAULT_TCL_PORT = 6666
DEFAULT_FLASH_BASE = 0x08000000
