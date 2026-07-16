import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6 import QtCore, QtWidgets, QtGui
import config
from ui import theme
from ui.data_source_dialog import DataSourceDialog
from ui.first_run_wizard import FirstRunWizard
from data.database import init_schema
from data.repositories.portfolios import list_portfolios
from ui.portfolios_view import PortfoliosView
from ui.transactions_view import TransactionsView
from data.events import event_bus


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("goqu")
        self.resize(1000, 650)

        self._build_menu_bar()
        init_schema()  # idempotent — must run before any widget that queries the DB
        self._build_central_layout()

        if not list_portfolios():
            QtCore.QTimer.singleShot(0, self._run_setup_wizard)

    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        # --- File menu ---
        file_menu = menu_bar.addMenu("&File")

        new_action = QtGui.QAction("&New", self)
        new_action.setShortcut(QtGui.QKeySequence.New)
        new_action.triggered.connect(lambda: self.statusBar().showMessage("New triggered", 2000))
        file_menu.addAction(new_action)

        open_action = QtGui.QAction("&Open...", self)
        open_action.setShortcut(QtGui.QKeySequence.Open)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        exit_action = QtGui.QAction("E&xit", self)
        exit_action.setShortcut(QtGui.QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Edit menu ---
        edit_menu = menu_bar.addMenu("&Edit")
        edit_menu.addAction(QtGui.QAction("Cut", self))
        edit_menu.addAction(QtGui.QAction("Copy", self))
        edit_menu.addAction(QtGui.QAction("Paste", self))

        # --- Help menu ---
        help_menu = menu_bar.addMenu("&Help")
        about_action = QtGui.QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        # --- Settings menu ---
        settings_menu = menu_bar.addMenu("&Settings")
        choose_source_action = QtGui.QAction("Choose Data Source…", self)
        choose_source_action.triggered.connect(self._open_data_source_dialog)
        settings_menu.addAction(choose_source_action)

        settings_menu.addSeparator()
        self._build_appearance_menu(settings_menu.addMenu("Appearance"))

        self._build_status_bar()

    def _build_appearance_menu(self, menu: QtWidgets.QMenu):
        """Dark / Light / Follow System as an exclusive, checkable group."""
        self._theme_group = QtGui.QActionGroup(self)
        self._theme_group.setExclusive(True)
        current = config.get_theme_pref()
        for mode, label in [("dark", "Dark"), ("light", "Light"), ("system", "Follow System")]:
            action = QtGui.QAction(label, self, checkable=True)
            action.setChecked(mode == current)
            action.triggered.connect(lambda _checked=False, m=mode: self._set_theme(m))
            self._theme_group.addAction(action)
            menu.addAction(action)

    def _set_theme(self, mode: str):
        config.set_theme_pref(mode)
        app = QtWidgets.QApplication.instance()
        theme.apply(app, theme.resolve_mode(mode, app))

    def _build_status_bar(self):
        bar = QtWidgets.QStatusBar()
        dot = QtWidgets.QLabel("●")
        dot.setObjectName("StatusDot")
        text = QtWidgets.QLabel("goqu · local")
        text.setObjectName("StatusText")
        bar.addWidget(dot)
        bar.addWidget(text)
        self.setStatusBar(bar)

    def _build_central_layout(self):
        # Left-hand navigation list
        self.nav_list = QtWidgets.QListWidget()
        self.nav_list.setObjectName("Sidebar")
        self.nav_list.setFixedWidth(180)
        self.nav_list.addItems(["Home", "Portfolios", "Transactions", "About"])

        # Pages shown on the right, one per nav item, swapped via QStackedWidget
        self._portfolios_view = PortfoliosView()
        self._transactions_view = TransactionsView()
        # Recording a transaction changes holdings — refresh an open dashboard
        self._transactions_view.transaction_recorded.connect(
            self._portfolios_view.refresh_detail
        )
        # Live market-data changes refresh an open dashboard too. refresh_detail
        # is a no-op unless a portfolio dashboard is currently open, so these are
        # cheap. New data types added later just emit on the same bus.
        bus = event_bus()
        bus.daily_updated.connect(lambda *_: self._portfolios_view.refresh_detail())
        bus.quote_updated.connect(lambda *_: self._portfolios_view.refresh_detail())
        bus.dividends_updated.connect(lambda *_: self._portfolios_view.refresh_detail())
        # Splits/mergers rebuild holdings — refresh an open dashboard.
        bus.corporate_actions_updated.connect(lambda *_: self._portfolios_view.refresh_detail())
        # Enriched company names/sectors show up in the holdings table.
        bus.metadata_updated.connect(lambda *_: self._portfolios_view.refresh_detail())

        # On a theme switch, rebuild table/tile contents so the per-value data
        # colors (gains/losses) are re-read from the now-active theme.
        theme.theme_signals().theme_changed.connect(self._on_theme_changed)

        self.pages = QtWidgets.QStackedWidget()
        self.pages.addWidget(self._make_page("Home view"))
        self.pages.addWidget(self._portfolios_view)
        self.pages.addWidget(self._transactions_view)
        self.pages.addWidget(self._make_page("About view"))

        self.nav_list.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        self.nav_list.setCurrentRow(0)

        splitter = QtWidgets.QSplitter()
        splitter.addWidget(self.nav_list)
        splitter.addWidget(self.pages)
        splitter.setStretchFactor(0, 0)  # sidebar: fixed-ish
        splitter.setStretchFactor(1, 1)  # content: grows

        self.setCentralWidget(splitter)

    def _on_theme_changed(self, _mode: str):
        # Rebuild only the data-bearing views whose per-value colors come from
        # Python (setForeground / tile colors). Card/label chrome recolors itself
        # via the new stylesheet, so we avoid refresh() here — it would navigate
        # the Portfolios stack away from an open dashboard.
        self._portfolios_view.refresh_detail()
        self._transactions_view.refresh()

    def _on_nav_changed(self, index: int):
        # Refresh the transactions view's portfolio list when it's opened, so
        # portfolios created after startup show up in the selector.
        if self.pages.widget(index) is self._transactions_view:
            self._transactions_view.refresh()

    @staticmethod
    def _make_page(label_text):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.addWidget(QtWidgets.QLabel(label_text, alignment=QtCore.Qt.AlignCenter))
        return page

    def _run_setup_wizard(self):
        wizard = FirstRunWizard(self)
        wizard.setup_complete.connect(lambda _: self._on_setup_complete())
        # If the user closes the wizard without finishing, exit — there's no DB yet
        wizard.rejected.connect(QtWidgets.QApplication.quit)
        wizard.exec()

    def _on_setup_complete(self):
        self._portfolios_view.refresh()
        self.statusBar().showMessage("Portfolio created successfully.", 3000)

    def _open_data_source_dialog(self):
        dialog = DataSourceDialog(self)
        dialog.exec()

    def _show_about(self):
        QtWidgets.QMessageBox.information(self, "About", "My Application\nBuilt with PySide6")
