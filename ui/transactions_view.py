import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Signal
from data.repositories import cash as cashrepo
from data.repositories.accounts import (
    ACCOUNT_TYPES,
    create_account,
    delete_account,
    list_accounts,
)
from data.repositories.portfolios import (
    BUY,
    SELL,
    delete_transaction,
    get_transaction,
    get_transactions,
    list_portfolios,
    record_transaction,
    record_transactions_batch,
    update_transaction,
)
from ui import theme

# Account-filter sentinels (combo item data).
_FILTER_ALL = "__all__"
_FILTER_UNASSIGNED = "__unassigned__"


def _fmt_money(value) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _shares_spin() -> QtWidgets.QDoubleSpinBox:
    spin = QtWidgets.QDoubleSpinBox()
    spin.setDecimals(4)
    spin.setMaximum(1_000_000_000)
    spin.setGroupSeparatorShown(True)
    return spin


def _money_spin(prefix: str = "$") -> QtWidgets.QDoubleSpinBox:
    spin = QtWidgets.QDoubleSpinBox()
    spin.setDecimals(2)
    spin.setMaximum(10_000_000)
    spin.setPrefix(prefix)
    spin.setGroupSeparatorShown(True)
    return spin


def _date_edit() -> QtWidgets.QDateEdit:
    edit = QtWidgets.QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("yyyy-MM-dd")
    edit.setDate(QtCore.QDate.currentDate())
    edit.setMaximumDate(QtCore.QDate.currentDate())
    return edit


def _section_label(text: str) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text.upper())
    label.setObjectName("SectionLabel")
    return label


class _TransactionDialog(QtWidgets.QDialog):
    """Edit an existing buy/sell, prefilled from a transaction dict."""

    def __init__(self, parent, txn: dict, accounts: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Edit Transaction")
        self.setMinimumWidth(360)
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        self._type = QtWidgets.QComboBox()
        self._type.addItem("Buy", BUY)
        self._type.addItem("Sell", SELL)
        idx = self._type.findData(txn["transaction_type"])
        if idx >= 0:
            self._type.setCurrentIndex(idx)
        form.addRow("Action", self._type)

        self._ticker = QtWidgets.QLineEdit(txn["symbol"])
        self._ticker.setMaxLength(12)
        form.addRow("Ticker *", self._ticker)

        self._date = _date_edit()
        self._date.setDate(QtCore.QDate.fromString(str(txn["date"]), "yyyy-MM-dd"))
        form.addRow("Date", self._date)

        self._shares = _shares_spin()
        self._shares.setValue(txn["shares"])
        form.addRow("Shares *", self._shares)

        self._price = _money_spin()
        self._price.setValue(txn["price"])
        form.addRow("Price / Share *", self._price)

        self._fees = _money_spin()
        self._fees.setValue(txn["fees"])
        form.addRow("Fees", self._fees)

        self._account = QtWidgets.QComboBox()
        self._account.addItem("— No account —", None)
        for account in accounts:
            self._account.addItem(account["name"], account["id"])
        acct_idx = self._account.findData(txn.get("account_id"))
        if acct_idx >= 0:
            self._account.setCurrentIndex(acct_idx)
        form.addRow("Account", self._account)

        self._notes = QtWidgets.QLineEdit(txn.get("notes", ""))
        form.addRow("Notes", self._notes)
        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "symbol": self._ticker.text().strip().upper(),
            "date": self._date.date().toString(QtCore.Qt.ISODate),
            "transaction_type": self._type.currentData(),
            "shares": self._shares.value(),
            "price": self._price.value(),
            "fees": self._fees.value(),
            "notes": self._notes.text().strip(),
            "account_id": self._account.currentData(),
        }


class AccountsDialog(QtWidgets.QDialog):
    """Create, view, and delete the brokerage accounts of a portfolio."""

    def __init__(self, parent, portfolio_id: int):
        super().__init__(parent)
        self._portfolio_id = portfolio_id
        self.setWindowTitle("Manage Accounts")
        self.setMinimumWidth(480)
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self._list = QtWidgets.QTableWidget()
        self._list.setColumnCount(4)
        self._list.setHorizontalHeaderLabels(["Name", "Type", "Institution", ""])
        self._list.horizontalHeader().setStretchLastSection(False)
        self._list.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._list.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._list.verticalHeader().setVisible(False)
        layout.addWidget(self._list)

        layout.addWidget(_section_label("Add Account"))
        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        self._name = QtWidgets.QLineEdit()
        self._name.setPlaceholderText("e.g., Fidelity Taxable")
        form.addRow("Name *", self._name)
        self._type = QtWidgets.QComboBox()
        for value, label in ACCOUNT_TYPES.items():
            self._type.addItem(label, value)
        form.addRow("Type", self._type)
        self._institution = QtWidgets.QLineEdit()
        self._institution.setPlaceholderText("e.g., Fidelity  (optional)")
        form.addRow("Institution", self._institution)
        layout.addLayout(form)

        add_row = QtWidgets.QHBoxLayout()
        add_row.addStretch()
        add_btn = QtWidgets.QPushButton("Add Account")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self._add)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        close_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        close_box.rejected.connect(self.reject)
        close_box.accepted.connect(self.accept)
        layout.addWidget(close_box)

        self._reload()

    def _reload(self):
        accounts = list_accounts(self._portfolio_id)
        self._list.setRowCount(len(accounts))
        for r, a in enumerate(accounts):
            self._list.setItem(r, 0, QtWidgets.QTableWidgetItem(a["name"]))
            self._list.setItem(
                r, 1, QtWidgets.QTableWidgetItem(ACCOUNT_TYPES.get(a["account_type"], a["account_type"]))
            )
            self._list.setItem(r, 2, QtWidgets.QTableWidgetItem(a["institution"]))
            holder = QtWidgets.QWidget()
            box = QtWidgets.QHBoxLayout(holder)
            box.setContentsMargins(4, 0, 4, 0)
            delete = QtWidgets.QPushButton("Delete")
            delete.setObjectName("LinkButton")
            delete.setCursor(QtCore.Qt.PointingHandCursor)
            delete.clicked.connect(lambda _=False, i=a["id"]: self._delete(i))
            box.addWidget(delete)
            self._list.setCellWidget(r, 3, holder)
        self._list.resizeColumnsToContents()
        self._list.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self._list.setColumnWidth(3, 90)

    def _add(self):
        name = self._name.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, "Required", "Account name cannot be empty.")
            self._name.setFocus()
            return
        try:
            create_account(
                self._portfolio_id, name, self._type.currentData(),
                self._institution.text().strip(),
            )
        except Exception as e:  # e.g. duplicate name (UNIQUE portfolio,name)
            QtWidgets.QMessageBox.warning(self, "Could not add account", str(e))
            return
        self._name.clear()
        self._institution.clear()
        self._reload()

    def _delete(self, account_id: int):
        confirm = QtWidgets.QMessageBox.question(
            self, "Delete account?",
            "Delete this account? Its transactions and cash are kept but become "
            "unassigned.",
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return
        delete_account(account_id)
        self._reload()


class TransactionsView(QtWidgets.QWidget):
    """Record buys/sells against a portfolio — single or in batches."""

    transaction_recorded = Signal()

    # Batch table columns
    COL_TICKER, COL_DATE, COL_SHARES, COL_PRICE, COL_FEES, COL_REMOVE = range(6)
    # Trade-history columns (Symbol stretches; Actions holds edit/delete buttons)
    COL_TXN_SYMBOL = 2
    COL_TXN_ACTIONS = 8

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # --- Header: title + shared portfolio selector ---
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Transactions")
        title.setObjectName("Title")
        header.addWidget(title)
        header.addStretch()

        header.addWidget(_section_label("Portfolio"))
        self._portfolio_combo = QtWidgets.QComboBox()
        self._portfolio_combo.setMinimumWidth(200)
        self._portfolio_combo.currentIndexChanged.connect(self._on_portfolio_changed)
        header.addWidget(self._portfolio_combo)

        header.addWidget(_section_label("Account"))
        self._account_filter = QtWidgets.QComboBox()
        self._account_filter.setMinimumWidth(150)
        self._account_filter.currentIndexChanged.connect(self._on_account_filter_changed)
        header.addWidget(self._account_filter)

        self._manage_accounts_btn = QtWidgets.QPushButton("Accounts…")
        self._manage_accounts_btn.clicked.connect(self._open_accounts_dialog)
        header.addWidget(self._manage_accounts_btn)
        root.addLayout(header)

        # --- Body: swaps between "no portfolios" and the real content ---
        self._stack = QtWidgets.QStackedWidget()
        root.addWidget(self._stack, stretch=1)

        self._stack.addWidget(self._build_empty_state())
        self._stack.addWidget(self._build_content())

        self.refresh()

    # ---------- builders ----------

    def _build_empty_state(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        msg = QtWidgets.QLabel(
            "No portfolios yet.\nCreate one from the Portfolios tab to record transactions."
        )
        msg.setObjectName("EmptyText")
        msg.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(msg)
        return widget

    def _build_content(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._build_single_tab(), "Single")
        tabs.addTab(self._build_batch_tab(), "Batch")
        tabs.addTab(self._build_cash_tab(), "Cash")
        layout.addWidget(tabs)

        layout.addWidget(_section_label("Recent Transactions"))
        self._history = QtWidgets.QTableWidget()
        self._history.setColumnCount(9)
        self._history.setHorizontalHeaderLabels(
            ["Date", "Type", "Symbol", "Account", "Shares", "Price", "Fees", "Net Cash", ""]
        )
        header = self._history.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.COL_TXN_SYMBOL, QtWidgets.QHeaderView.Stretch)
        self._history.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._history.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._history.verticalHeader().setVisible(False)
        self._history.setAlternatingRowColors(True)
        layout.addWidget(self._history, stretch=1)

        return widget

    def _build_single_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(4, 12, 4, 4)

        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(QtCore.Qt.AlignRight)

        self._single_type = QtWidgets.QComboBox()
        self._single_type.addItem("Buy", BUY)
        self._single_type.addItem("Sell", SELL)
        form.addRow("Action", self._single_type)

        self._single_ticker = QtWidgets.QLineEdit()
        self._single_ticker.setPlaceholderText("e.g., AAPL")
        self._single_ticker.setMaxLength(12)
        form.addRow("Ticker *", self._single_ticker)

        self._single_date = _date_edit()
        form.addRow("Date", self._single_date)

        self._single_shares = _shares_spin()
        form.addRow("Shares *", self._single_shares)

        self._single_price = _money_spin()
        form.addRow("Price / Share *", self._single_price)

        self._single_fees = _money_spin()
        form.addRow("Fees", self._single_fees)

        self._single_account = QtWidgets.QComboBox()
        form.addRow("Account", self._single_account)

        self._single_notes = QtWidgets.QLineEdit()
        self._single_notes.setPlaceholderText("Optional")
        form.addRow("Notes", self._single_notes)

        outer.addLayout(form)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        record_btn = QtWidgets.QPushButton("Record Transaction")
        record_btn.setObjectName("PrimaryButton")
        record_btn.clicked.connect(self._record_single)
        btn_row.addWidget(record_btn)
        outer.addLayout(btn_row)
        outer.addStretch()
        return tab

    def _build_batch_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(4, 12, 4, 4)
        outer.setSpacing(10)

        # Batch-wide action selector. Each row carries its own date, so the batch
        # naturally spans a timeframe.
        top = QtWidgets.QHBoxLayout()
        top.addWidget(_section_label("Action"))
        self._batch_type = QtWidgets.QComboBox()
        self._batch_type.addItem("Buy", BUY)
        self._batch_type.addItem("Sell", SELL)
        top.addWidget(self._batch_type)
        top.addWidget(_section_label("Account"))
        self._batch_account = QtWidgets.QComboBox()
        self._batch_account.setMinimumWidth(150)
        top.addWidget(self._batch_account)
        top.addStretch()
        add_btn = QtWidgets.QPushButton("+ Add Row")
        add_btn.clicked.connect(lambda: self._add_batch_row())
        top.addWidget(add_btn)
        outer.addLayout(top)

        self._batch_table = QtWidgets.QTableWidget()
        self._batch_table.setColumnCount(6)
        self._batch_table.setHorizontalHeaderLabels(
            ["Ticker", "Date", "Shares", "Price", "Fees", ""]
        )
        self._batch_table.horizontalHeader().setSectionResizeMode(
            self.COL_TICKER, QtWidgets.QHeaderView.Stretch
        )
        self._batch_table.verticalHeader().setVisible(False)
        outer.addWidget(self._batch_table, stretch=1)

        for _ in range(3):
            self._add_batch_row()

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        record_all = QtWidgets.QPushButton("Record All")
        record_all.setObjectName("PrimaryButton")
        record_all.clicked.connect(self._record_batch)
        btn_row.addWidget(record_all)
        outer.addLayout(btn_row)
        return tab

    # Cash-history columns (Notes stretches; Actions holds the delete button)
    COL_CASH_NOTES = 4
    COL_CASH_ACTIONS = 5

    def _build_cash_tab(self) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(4, 12, 4, 4)
        outer.setSpacing(12)

        # Running balance banner
        bal_row = QtWidgets.QHBoxLayout()
        bal_row.addWidget(_section_label("Cash Balance"))
        self._cash_balance = QtWidgets.QLabel("—")
        self._cash_balance.setObjectName("DataValue")
        bal_row.addWidget(self._cash_balance)
        bal_row.addStretch()
        outer.addLayout(bal_row)

        # Entry form
        form = QtWidgets.QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        self._cash_type = QtWidgets.QComboBox()
        for cash_type in cashrepo.CASH_TYPES:
            self._cash_type.addItem(cash_type.capitalize(), cash_type)
        form.addRow("Type", self._cash_type)
        self._cash_amount = _money_spin()
        self._cash_amount.setMinimum(-10_000_000)  # allow negative adjustments
        form.addRow("Amount *", self._cash_amount)
        self._cash_date = _date_edit()
        form.addRow("Date", self._cash_date)
        self._cash_account = QtWidgets.QComboBox()
        form.addRow("Account", self._cash_account)
        self._cash_notes = QtWidgets.QLineEdit()
        self._cash_notes.setPlaceholderText("Optional")
        form.addRow("Notes", self._cash_notes)
        outer.addLayout(form)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        record = QtWidgets.QPushButton("Record Cash")
        record.setObjectName("PrimaryButton")
        record.clicked.connect(self._record_cash)
        btn_row.addWidget(record)
        outer.addLayout(btn_row)

        # Cash history
        outer.addWidget(_section_label("Cash History"))
        self._cash_history = QtWidgets.QTableWidget()
        self._cash_history.setColumnCount(6)
        self._cash_history.setHorizontalHeaderLabels(
            ["Date", "Type", "Account", "Amount", "Notes", ""]
        )
        ch = self._cash_history.horizontalHeader()
        ch.setStretchLastSection(False)
        ch.setSectionResizeMode(self.COL_CASH_NOTES, QtWidgets.QHeaderView.Stretch)
        self._cash_history.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._cash_history.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._cash_history.verticalHeader().setVisible(False)
        self._cash_history.setAlternatingRowColors(True)
        outer.addWidget(self._cash_history, stretch=1)
        return tab

    def _reload_cash(self):
        portfolio_id = self._current_portfolio_id()
        if portfolio_id is None:
            return
        summary = cashrepo.get_cash_summary(portfolio_id)
        balance = summary["balance"]
        self._cash_balance.setText(_fmt_money(balance))
        theme.set_pl_property(self._cash_balance, theme.pl_kind(balance))

        keep = self._account_predicate()
        rows = [c for c in cashrepo.get_cash_transactions(portfolio_id) if keep(c)]
        self._cash_history.setRowCount(len(rows))
        for r, c in enumerate(rows):
            amount = c["amount"]
            cells = [
                (str(c["date"]), None, QtCore.Qt.AlignLeft),
                (c["cash_type"].capitalize(), None, QtCore.Qt.AlignLeft),
                (c["account_name"] or "—", theme.muted() if not c["account_name"] else None,
                 QtCore.Qt.AlignLeft),
                (_fmt_money(amount), theme.gain() if amount >= 0 else theme.loss(),
                 QtCore.Qt.AlignRight),
                (c.get("notes", ""), None, QtCore.Qt.AlignLeft),
            ]
            for col, (text, color, align) in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(align | QtCore.Qt.AlignVCenter)
                if color is not None:
                    item.setForeground(color)
                self._cash_history.setItem(r, col, item)
            self._cash_history.setCellWidget(
                r, self.COL_CASH_ACTIONS, self._cash_delete_action(c["id"])
            )
        self._cash_history.resizeColumnsToContents()
        self._cash_history.horizontalHeader().setSectionResizeMode(
            self.COL_CASH_NOTES, QtWidgets.QHeaderView.Stretch
        )
        self._cash_history.setColumnWidth(self.COL_CASH_ACTIONS, 90)  # fit Delete

    def _cash_delete_action(self, cash_id: int) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(4, 0, 4, 0)
        delete = QtWidgets.QPushButton("Delete")
        delete.setObjectName("LinkButton")
        delete.setCursor(QtCore.Qt.PointingHandCursor)
        delete.clicked.connect(lambda _=False, i=cash_id: self._delete_cash(i))
        row.addWidget(delete)
        return holder

    def _record_cash(self):
        portfolio_id = self._current_portfolio_id()
        if portfolio_id is None:
            return
        magnitude = self._cash_amount.value()
        if magnitude == 0:
            self._warn("Amount must be non-zero.")
            self._cash_amount.setFocus()
            return
        cash_type = self._cash_type.currentData()
        cashrepo.record_cash_transaction(
            portfolio_id,
            self._cash_date.date().toString(QtCore.Qt.ISODate),
            cash_type,
            cashrepo.signed_amount(cash_type, magnitude),
            self._cash_notes.text().strip(),
            account_id=self._cash_account.currentData(),
        )
        self._cash_amount.setValue(0)
        self._cash_notes.clear()
        self._reload_cash()
        self.transaction_recorded.emit()

    def _delete_cash(self, cash_id: int):
        cashrepo.delete_cash_transaction(cash_id)
        self._reload_cash()
        self.transaction_recorded.emit()

    def _add_batch_row(self):
        row = self._batch_table.rowCount()
        self._batch_table.insertRow(row)

        ticker = QtWidgets.QLineEdit()
        ticker.setPlaceholderText("TICKER")
        ticker.setMaxLength(12)
        self._batch_table.setCellWidget(row, self.COL_TICKER, ticker)
        self._batch_table.setCellWidget(row, self.COL_DATE, _date_edit())
        self._batch_table.setCellWidget(row, self.COL_SHARES, _shares_spin())
        self._batch_table.setCellWidget(row, self.COL_PRICE, _money_spin())
        self._batch_table.setCellWidget(row, self.COL_FEES, _money_spin())

        remove = QtWidgets.QPushButton("✕")
        remove.setFixedWidth(28)
        remove.setToolTip("Remove row")
        remove.clicked.connect(lambda: self._remove_batch_row(remove))
        self._batch_table.setCellWidget(row, self.COL_REMOVE, remove)
        self._batch_table.resizeColumnsToContents()
        self._batch_table.horizontalHeader().setSectionResizeMode(
            self.COL_TICKER, QtWidgets.QHeaderView.Stretch
        )

    def _remove_batch_row(self, button: QtWidgets.QPushButton):
        for row in range(self._batch_table.rowCount()):
            if self._batch_table.cellWidget(row, self.COL_REMOVE) is button:
                self._batch_table.removeRow(row)
                return

    # ---------- data ----------

    def refresh(self):
        """Reload the portfolio list (preserving selection) and the history table."""
        portfolios = list_portfolios()
        if not portfolios:
            self._stack.setCurrentIndex(0)
            return

        previous_id = self._current_portfolio_id()
        self._portfolio_combo.blockSignals(True)
        self._portfolio_combo.clear()
        for p in portfolios:
            self._portfolio_combo.addItem(p["name"], p["id"])
        # Restore prior selection if it still exists
        if previous_id is not None:
            idx = self._portfolio_combo.findData(previous_id)
            if idx >= 0:
                self._portfolio_combo.setCurrentIndex(idx)
        self._portfolio_combo.blockSignals(False)

        self._stack.setCurrentIndex(1)
        self._reload_accounts()
        self._reload_history()
        self._reload_cash()

    def _current_portfolio_id(self):
        if self._portfolio_combo.count() == 0:
            return None
        return self._portfolio_combo.currentData()

    def _on_portfolio_changed(self, _index: int):
        self._reload_accounts()
        self._reload_history()
        self._reload_cash()

    # ---------- accounts ----------

    def _reload_accounts(self):
        """Repopulate every account combo (entry selectors + header filter) from
        the current portfolio's accounts, preserving selections where possible."""
        portfolio_id = self._current_portfolio_id()
        accounts = list_accounts(portfolio_id) if portfolio_id is not None else []
        for combo in (self._single_account, self._batch_account, self._cash_account):
            self._fill_account_combo(combo, accounts, is_filter=False)
        self._fill_account_combo(self._account_filter, accounts, is_filter=True)

    @staticmethod
    def _fill_account_combo(combo: QtWidgets.QComboBox, accounts: list[dict], *, is_filter: bool):
        previous = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        if is_filter:
            combo.addItem("All accounts", _FILTER_ALL)
            combo.addItem("Unassigned", _FILTER_UNASSIGNED)
        else:
            combo.addItem("— No account —", None)
        for account in accounts:
            combo.addItem(account["name"], account["id"])
        idx = combo.findData(previous)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _account_predicate(self):
        """Row filter from the header account selector (applies to both histories)."""
        data = self._account_filter.currentData() if hasattr(self, "_account_filter") else _FILTER_ALL
        if data == _FILTER_UNASSIGNED:
            return lambda row: row["account_id"] is None
        if isinstance(data, int):
            return lambda row: row["account_id"] == data
        return lambda row: True

    def _on_account_filter_changed(self, _index: int):
        self._reload_history()
        self._reload_cash()

    def _open_accounts_dialog(self):
        portfolio_id = self._current_portfolio_id()
        if portfolio_id is None:
            return
        AccountsDialog(self, portfolio_id).exec()
        # Accounts may have been added/removed — refresh selectors + histories.
        self._reload_accounts()
        self._reload_history()
        self._reload_cash()

    def _reload_history(self):
        portfolio_id = self._current_portfolio_id()
        if portfolio_id is None:
            return
        keep = self._account_predicate()
        txns = [t for t in get_transactions(portfolio_id) if keep(t)]
        self._history.setRowCount(len(txns))
        for r, t in enumerate(txns):
            is_buy = t["transaction_type"] == BUY
            gross = t["shares"] * t["price"]
            # Buys are cash out (negative), sells are cash in (positive)
            net_cash = -(gross + t["fees"]) if is_buy else (gross - t["fees"])
            cells = [
                (str(t["date"]), None, QtCore.Qt.AlignLeft),
                (t["transaction_type"].upper(), theme.gain() if is_buy else theme.loss(), QtCore.Qt.AlignLeft),
                (t["symbol"], None, QtCore.Qt.AlignLeft),
                (t["account_name"] or "—", theme.muted() if not t["account_name"] else None, QtCore.Qt.AlignLeft),
                (f"{t['shares']:,.4f}".rstrip("0").rstrip("."), None, QtCore.Qt.AlignRight),
                (_fmt_money(t["price"]), None, QtCore.Qt.AlignRight),
                (_fmt_money(t["fees"]), None, QtCore.Qt.AlignRight),
                (_fmt_money(net_cash), theme.gain() if net_cash >= 0 else theme.loss(), QtCore.Qt.AlignRight),
            ]
            for c, (text, color, align) in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(align | QtCore.Qt.AlignVCenter)
                if color is not None:
                    item.setForeground(color)
                self._history.setItem(r, c, item)
            self._history.setCellWidget(
                r, self.COL_TXN_ACTIONS, self._row_actions(t["id"])
            )
        self._history.resizeColumnsToContents()
        self._history.horizontalHeader().setSectionResizeMode(
            self.COL_TXN_SYMBOL, QtWidgets.QHeaderView.Stretch
        )
        self._history.setColumnWidth(self.COL_TXN_ACTIONS, 140)  # fit Edit + Delete

    def _row_actions(self, txn_id: int) -> QtWidgets.QWidget:
        """Edit + Delete buttons for a trade-history row (capture the txn id, not
        the row index, so they stay correct as rows shift)."""
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(2)
        edit = QtWidgets.QPushButton("Edit")
        edit.setObjectName("LinkButton")
        edit.setCursor(QtCore.Qt.PointingHandCursor)
        edit.clicked.connect(lambda _=False, i=txn_id: self._edit_transaction(i))
        delete = QtWidgets.QPushButton("Delete")
        delete.setObjectName("LinkButton")
        delete.setCursor(QtCore.Qt.PointingHandCursor)
        delete.clicked.connect(lambda _=False, i=txn_id: self._delete_transaction(i))
        row.addWidget(edit)
        row.addWidget(delete)
        return holder

    # ---------- edit / delete ----------

    def _edit_transaction(self, txn_id: int):
        txn = get_transaction(txn_id)
        if txn is None:
            return
        dialog = _TransactionDialog(self, txn, list_accounts(txn["portfolio_id"]))
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        values = dialog.values()
        if not values["symbol"]:
            self._warn("Ticker is required.")
            return
        if values["shares"] <= 0:
            self._warn("Shares must be greater than zero.")
            return
        update_transaction(txn_id, **values)
        self._reload_history()
        self.transaction_recorded.emit()

    def _delete_transaction(self, txn_id: int):
        txn = get_transaction(txn_id)
        if txn is None:
            return
        summary = f"{txn['transaction_type'].upper()} {txn['shares']:g} {txn['symbol']} on {txn['date']}"
        confirm = QtWidgets.QMessageBox.question(
            self, "Delete transaction?",
            f"Delete this transaction?\n\n{summary}\n\nHoldings will be recomputed.",
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return
        delete_transaction(txn_id)
        self._reload_history()
        self.transaction_recorded.emit()

    # ---------- actions ----------

    def _record_single(self):
        portfolio_id = self._current_portfolio_id()
        if portfolio_id is None:
            return
        ticker = self._single_ticker.text().strip().upper()
        shares = self._single_shares.value()
        price = self._single_price.value()
        if not ticker:
            self._warn("Ticker is required.")
            self._single_ticker.setFocus()
            return
        if shares <= 0:
            self._warn("Shares must be greater than zero.")
            self._single_shares.setFocus()
            return

        record_transaction(
            portfolio_id=portfolio_id,
            symbol=ticker,
            date=self._single_date.date().toString(QtCore.Qt.ISODate),
            transaction_type=self._single_type.currentData(),
            shares=shares,
            price=price,
            fees=self._single_fees.value(),
            notes=self._single_notes.text().strip(),
            account_id=self._single_account.currentData(),
        )
        # Reset the entry fields for the next record
        self._single_ticker.clear()
        self._single_shares.setValue(0)
        self._single_price.setValue(0)
        self._single_fees.setValue(0)
        self._single_notes.clear()

        self._reload_history()
        self.transaction_recorded.emit()

    def _record_batch(self):
        portfolio_id = self._current_portfolio_id()
        if portfolio_id is None:
            return

        txn_type = self._batch_type.currentData()
        rows = []
        for row in range(self._batch_table.rowCount()):
            ticker = self._batch_table.cellWidget(row, self.COL_TICKER).text().strip().upper()
            shares = self._batch_table.cellWidget(row, self.COL_SHARES).value()
            price = self._batch_table.cellWidget(row, self.COL_PRICE).value()
            fees = self._batch_table.cellWidget(row, self.COL_FEES).value()
            date = self._batch_table.cellWidget(row, self.COL_DATE).date().toString(QtCore.Qt.ISODate)

            # Skip fully-empty rows so users can leave spare rows around
            if not ticker and shares == 0 and price == 0:
                continue
            if not ticker:
                self._warn(f"Row {row + 1}: ticker is required.")
                return
            if shares <= 0:
                self._warn(f"Row {row + 1} ({ticker}): shares must be greater than zero.")
                return
            rows.append({
                "symbol": ticker,
                "date": date,
                "transaction_type": txn_type,
                "shares": shares,
                "price": price,
                "fees": fees,
            })

        if not rows:
            self._warn("Add at least one transaction row.")
            return

        count = record_transactions_batch(
            portfolio_id, rows, account_id=self._batch_account.currentData()
        )

        # Reset to a fresh set of blank rows
        self._batch_table.setRowCount(0)
        for _ in range(3):
            self._add_batch_row()

        self._reload_history()
        self.transaction_recorded.emit()
        QtWidgets.QMessageBox.information(
            self, "Recorded", f"Recorded {count} transaction(s)."
        )

    def _warn(self, message: str):
        QtWidgets.QMessageBox.warning(self, "Check your entry", message)
