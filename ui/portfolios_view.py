import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Signal
from data.repositories.portfolios import create_portfolio, list_portfolios
from ui.portfolio_detail_view import PortfolioDetailView


class NewPortfolioDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Portfolio")
        self.setMinimumWidth(400)
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        form.setSpacing(10)

        self._name_edit = QtWidgets.QLineEdit()
        self._name_edit.setPlaceholderText("e.g., Retirement Fund, Tech Growth")
        form.addRow("Portfolio Name *", self._name_edit)

        self._desc_edit = QtWidgets.QPlainTextEdit()
        self._desc_edit.setPlaceholderText("Optional description…")
        self._desc_edit.setFixedHeight(68)
        form.addRow("Description", self._desc_edit)

        self._benchmark_edit = QtWidgets.QLineEdit()
        self._benchmark_edit.setPlaceholderText("e.g., SPY, QQQ  (optional)")
        self._benchmark_edit.setMaximumWidth(160)
        form.addRow("Benchmark Ticker", self._benchmark_edit)

        layout.addLayout(form)
        layout.addStretch()

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Required", "Portfolio name cannot be empty.")
            self._name_edit.setFocus()
            return
        create_portfolio(
            name=name,
            description=self._desc_edit.toPlainText().strip(),
            benchmark_ticker=self._benchmark_edit.text().strip(),
        )
        self.accept()


class _PortfolioCard(QtWidgets.QFrame):
    clicked = Signal(int)  # emits the portfolio id

    def __init__(self, portfolio: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._portfolio_id = portfolio["id"]
        self.setCursor(QtCore.Qt.PointingHandCursor)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        info = QtWidgets.QVBoxLayout()
        info.setSpacing(4)

        name_label = QtWidgets.QLabel(portfolio["name"])
        name_label.setObjectName("CardName")
        info.addWidget(name_label)

        if portfolio.get("description"):
            desc_label = QtWidgets.QLabel(portfolio["description"])
            desc_label.setObjectName("CardMeta")
            desc_label.setWordWrap(True)
            info.addWidget(desc_label)

        layout.addLayout(info, stretch=1)

        date_str = portfolio.get("created_at", "")
        if date_str:
            # created_at is ISO datetime; show only the date part
            date_label = QtWidgets.QLabel(date_str[:10])
            date_label.setObjectName("CardMeta")
            date_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            layout.addWidget(date_label)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit(self._portfolio_id)
        super().mouseReleaseEvent(event)


class PortfoliosView(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Header row (hidden while viewing a portfolio's detail)
        self._header = QtWidgets.QWidget()
        header = QtWidgets.QHBoxLayout(self._header)
        header.setContentsMargins(0, 0, 0, 0)
        title = QtWidgets.QLabel("Portfolios")
        title.setObjectName("Title")
        header.addWidget(title)
        header.addStretch()

        self._new_btn = QtWidgets.QPushButton("+ New Portfolio")
        self._new_btn.setObjectName("PrimaryButton")
        self._new_btn.clicked.connect(self._open_new_dialog)
        header.addWidget(self._new_btn)
        root.addWidget(self._header)

        # Body: switches between empty state and card list
        self._stack = QtWidgets.QStackedWidget()
        root.addWidget(self._stack)

        # Empty state
        empty_widget = QtWidgets.QWidget()
        empty_layout = QtWidgets.QVBoxLayout(empty_widget)
        empty_layout.setAlignment(QtCore.Qt.AlignCenter)
        empty_label = QtWidgets.QLabel("No portfolios yet.")
        empty_label.setObjectName("EmptyText")
        empty_label.setAlignment(QtCore.Qt.AlignCenter)
        empty_layout.addWidget(empty_label)

        create_link = QtWidgets.QPushButton("Create one now")
        create_link.setFlat(True)
        create_link.setCursor(QtCore.Qt.PointingHandCursor)
        create_link.clicked.connect(self._open_new_dialog)
        empty_layout.addWidget(create_link, alignment=QtCore.Qt.AlignCenter)
        self._stack.addWidget(empty_widget)

        # Card list inside a scroll area
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._card_container = QtWidgets.QWidget()
        self._card_layout = QtWidgets.QVBoxLayout(self._card_container)
        self._card_layout.setSpacing(10)
        self._card_layout.setAlignment(QtCore.Qt.AlignTop)
        self._scroll.setWidget(self._card_container)
        self._stack.addWidget(self._scroll)

        # Detail view (page index 2)
        self._detail_view = PortfolioDetailView()
        self._detail_view.back_requested.connect(self._show_list)
        self._stack.addWidget(self._detail_view)

        self.refresh()

    def refresh(self):
        portfolios = list_portfolios()
        if not portfolios:
            self._stack.setCurrentIndex(0)
            return

        # Rebuild the card list
        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for p in portfolios:
            card = _PortfolioCard(p)
            card.clicked.connect(self._show_detail)
            self._card_layout.addWidget(card)

        self._stack.setCurrentIndex(1)

    def _show_detail(self, portfolio_id: int):
        self._detail_view.load(portfolio_id)
        self._header.setVisible(False)
        self._stack.setCurrentIndex(2)

    def _show_list(self):
        self._header.setVisible(True)
        self.refresh()

    def refresh_detail(self):
        """Refresh the open portfolio dashboard, if one is currently shown.
        Hook for external data changes (transactions, future real-time feeds)."""
        if self._stack.currentWidget() is self._detail_view:
            self._detail_view.refresh()

    def _open_new_dialog(self):
        dialog = NewPortfolioDialog(self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.refresh()
