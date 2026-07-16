import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Signal
from data.repositories.portfolios import create_portfolio


class WelcomePage(QtWidgets.QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Welcome to goqu")
        self.setSubTitle("Your personal portfolio analytics platform.")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)

        body = QtWidgets.QLabel(
            "goqu tracks your portfolios, logs your trades, and runs quantitative "
            "analysis — all stored locally on your machine.\n\n"
            "Let's create your first portfolio to get started. "
            "This will also set up a local database at:\n"
            f"  ~/.config/goqu/goqu.db"
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch()


class PortfolioPage(QtWidgets.QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle("Create Your First Portfolio")
        self.setSubTitle("You can create more portfolios later from the Portfolios view.")

        form = QtWidgets.QFormLayout(self)
        form.setSpacing(12)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        self._name_edit = QtWidgets.QLineEdit()
        self._name_edit.setPlaceholderText("e.g., Retirement Fund, Tech Growth")
        form.addRow("Portfolio Name *", self._name_edit)
        # Registering with * makes the Next/Finish button require a non-empty value
        self.registerField("portfolio_name*", self._name_edit)

        self._desc_edit = QtWidgets.QPlainTextEdit()
        self._desc_edit.setPlaceholderText("Optional description…")
        self._desc_edit.setFixedHeight(72)
        form.addRow("Description", self._desc_edit)

        self._benchmark_edit = QtWidgets.QLineEdit()
        self._benchmark_edit.setPlaceholderText("e.g., SPY, QQQ  (optional)")
        self._benchmark_edit.setMaximumWidth(160)
        form.addRow("Benchmark Ticker", self._benchmark_edit)
        self.registerField("benchmark_ticker", self._benchmark_edit)

    def description_text(self) -> str:
        return self._desc_edit.toPlainText().strip()


class FirstRunWizard(QtWidgets.QWizard):
    """Runs on first launch to initialize the database and create the first portfolio."""

    setup_complete = Signal(int)  # emits the new portfolio id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("goqu — Initial Setup")
        self.setMinimumSize(560, 380)
        self.setWizardStyle(QtWidgets.QWizard.ModernStyle)
        self.setOption(QtWidgets.QWizard.NoBackButtonOnStartPage, True)

        self.addPage(WelcomePage())
        self._portfolio_page = PortfolioPage()
        self.addPage(self._portfolio_page)

        self.button(QtWidgets.QWizard.FinishButton).setText("Create Portfolio")

    def accept(self):
        portfolio_id = create_portfolio(
            name=self.field("portfolio_name").strip(),
            description=self._portfolio_page.description_text(),
            benchmark_ticker=self.field("benchmark_ticker").strip(),
        )
        self.setup_complete.emit(portfolio_id)
        super().accept()
