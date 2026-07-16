import sys
import os

# Ensure project root is on path so config is importable regardless of how the dialog is opened
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6 import QtCore, QtWidgets
from config import SOURCES, load_datasource_config, save_datasource_config


class DataSourceDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Data Source")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._config = load_datasource_config()
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        form.setSpacing(10)

        self._source_combo = QtWidgets.QComboBox()
        self._source_combo.addItems(SOURCES)
        form.addRow("Data Source:", self._source_combo)

        layout.addLayout(form)

        # Separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        layout.addWidget(line)

        # Source-specific section
        self._detail_form = QtWidgets.QFormLayout()
        self._detail_form.setLabelAlignment(QtCore.Qt.AlignRight)
        self._detail_form.setSpacing(10)

        self._info_label = QtWidgets.QLabel(
            "yfinance is open-source and requires no API key."
        )
        self._info_label.setWordWrap(True)
        self._info_label.setObjectName("MutedItalic")
        self._detail_form.addRow(self._info_label)

        self._api_key_label = QtWidgets.QLabel("API Key:")
        self._api_key_edit = QtWidgets.QLineEdit()
        self._api_key_edit.setPlaceholderText("Enter your API key…")
        self._api_key_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self._detail_form.addRow(self._api_key_label, self._api_key_edit)

        self._proxy_edit = QtWidgets.QLineEdit()
        self._proxy_edit.setPlaceholderText("http://proxy:port  (optional)")
        self._detail_form.addRow("Proxy:", self._proxy_edit)

        layout.addLayout(self._detail_form)
        layout.addStretch()

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self._save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._source_combo.currentTextChanged.connect(self._on_source_changed)

    def _load_values(self):
        source = self._config.get("source", SOURCES[0])
        idx = self._source_combo.findText(source)
        self._source_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._api_key_edit.setText(self._config.get("api_key", ""))
        self._proxy_edit.setText(self._config.get("proxy", ""))
        self._on_source_changed(self._source_combo.currentText())

    def _on_source_changed(self, source: str):
        needs_key = source != "yfinance"
        self._info_label.setVisible(not needs_key)
        self._api_key_label.setVisible(needs_key)
        self._api_key_edit.setVisible(needs_key)

    def _save(self):
        source = self._source_combo.currentText()
        api_key = self._api_key_edit.text().strip() if source != "yfinance" else ""
        config = {
            "source": source,
            "api_key": api_key,
            "proxy": self._proxy_edit.text().strip(),
        }
        save_datasource_config(config)
        self.accept()
