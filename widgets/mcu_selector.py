"""MCU selector widget — STM32 family tree with custom config option."""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QPushButton, QFileDialog, QGroupBox
)
from PyQt5.QtCore import Qt, pyqtSignal

from mcu_config import STM32_FAMILIES


_CUSTOM_KEY = "__custom__"


class MCUSelectorWidget(QWidget):
    sig_target_changed = pyqtSignal(str, str)  # (family_name, target_cfg_path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_target = ""
        self._setup_ui()
        self._populate_tree()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel("<b>Target MCU</b>")
        layout.addWidget(title)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

        # Selected config display
        self._selected_label = QLabel("No target selected")
        self._selected_label.setWordWrap(True)
        self._selected_label.setStyleSheet("color: #aaaaaa; font-size: 9pt;")
        layout.addWidget(self._selected_label)

        # Custom config group
        grp = QGroupBox("Custom Config")
        grp_layout = QHBoxLayout(grp)
        grp_layout.setContentsMargins(4, 4, 4, 4)
        self._custom_edit = QLineEdit()
        self._custom_edit.setPlaceholderText("path/to/target.cfg")
        self._custom_edit.textChanged.connect(self._on_custom_changed)
        grp_layout.addWidget(self._custom_edit)
        btn = QPushButton("...")
        btn.setFixedWidth(28)
        btn.clicked.connect(self._browse_custom)
        grp_layout.addWidget(btn)
        layout.addWidget(grp)

    def _populate_tree(self):
        self._tree.clear()
        for family, info in STM32_FAMILIES.items():
            family_item = QTreeWidgetItem(self._tree, [family])
            family_item.setData(0, Qt.UserRole, info["target_config"])
            family_item.setToolTip(0, info["description"])
            for series in info.get("series", []):
                child = QTreeWidgetItem(family_item, [series])
                child.setData(0, Qt.UserRole, info["target_config"])
                child.setToolTip(0, f"{family} {series} — {info['description']}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def target_config(self) -> str:
        return self._current_target

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        cfg = item.data(0, Qt.UserRole)
        if cfg:
            self._current_target = cfg
            self._selected_label.setText(cfg)
            # Clear custom field to avoid confusion
            self._custom_edit.blockSignals(True)
            self._custom_edit.clear()
            self._custom_edit.blockSignals(False)
            # Determine display name
            parent = item.parent()
            if parent:
                name = f"{parent.text(0)} {item.text(0)}"
            else:
                name = item.text(0)
            self.sig_target_changed.emit(name, cfg)

    def _on_custom_changed(self, text: str):
        text = text.strip()
        if text:
            self._current_target = text
            self._selected_label.setText(text)
            self._tree.clearSelection()
            self.sig_target_changed.emit("Custom", text)

    def _browse_custom(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select OpenOCD Target Config", "",
            "Config Files (*.cfg);;All Files (*)"
        )
        if path:
            self._custom_edit.setText(path)
