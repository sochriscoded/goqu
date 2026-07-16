import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Signal
from data.repositories.analytics import get_latest_optimization, get_latest_risk_metrics
from data.repositories.cash import get_cash_summary
from data.repositories.income import get_dividend_income, get_income_summary
from data.repositories.portfolios import get_holdings, get_portfolio
from ui import theme


def _fmt_money(value) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _fmt_pct(value) -> str:
    if value is None:
        return "—"
    return f"{value:+.2f}%"


class _MetricTile(QtWidgets.QFrame):
    """A small labeled stat panel: caption on top, big value below. Styling comes
    from the theme stylesheet (object names + the dynamic `pl` property)."""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setObjectName("MetricTile")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)

        self._caption = QtWidgets.QLabel(caption.upper())
        self._caption.setObjectName("MetricCaption")
        layout.addWidget(self._caption)

        self._value = QtWidgets.QLabel("—")
        self._value.setObjectName("MetricValue")
        layout.addWidget(self._value)

    def set_value(self, text: str, kind: str | None = None):
        """`kind` is 'gain' | 'loss' | 'muted' | None — a theme-aware category
        that recolors automatically when the theme changes."""
        self._value.setText(text)
        theme.set_pl_property(self._value, kind)


def _section_label(text: str) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text.upper())
    label.setObjectName("SectionLabel")
    return label


class PortfolioDetailView(QtWidgets.QWidget):
    """High-level dashboard for a single portfolio."""

    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._portfolio_id: int | None = None

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # --- Top bar: back button + portfolio name ---
        top_bar = QtWidgets.QHBoxLayout()
        self._back_btn = QtWidgets.QPushButton("←  Back")
        self._back_btn.setFlat(True)
        self._back_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(self._back_btn)
        top_bar.addStretch()
        root.addLayout(top_bar)

        self._name_label = QtWidgets.QLabel()
        self._name_label.setObjectName("Title")
        root.addWidget(self._name_label)

        self._desc_label = QtWidgets.QLabel()
        self._desc_label.setObjectName("Subtitle")
        self._desc_label.setWordWrap(True)
        root.addWidget(self._desc_label)

        # Everything below scrolls, so the dashboard works on small windows
        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        self._scroll.setWidget(content)
        root.addWidget(self._scroll, stretch=1)

        body = QtWidgets.QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(18)

        # --- Summary metric tiles ---
        tiles_row = QtWidgets.QHBoxLayout()
        tiles_row.setSpacing(12)
        self._tile_total = _MetricTile("Total Value")
        self._tile_value = _MetricTile("Market Value")
        self._tile_cash = _MetricTile("Cash")
        self._tile_pl = _MetricTile("Unrealized P/L")
        self._tile_return = _MetricTile("Total Return")
        self._tile_holdings = _MetricTile("Holdings")
        for tile in (
            self._tile_total,
            self._tile_value,
            self._tile_cash,
            self._tile_pl,
            self._tile_return,
            self._tile_holdings,
        ):
            tiles_row.addWidget(tile)
        body.addLayout(tiles_row)

        # --- Holdings table ---
        body.addWidget(_section_label("Holdings"))
        self._holdings_stack = QtWidgets.QStackedWidget()
        self._holdings_table = QtWidgets.QTableWidget()
        self._holdings_table.setColumnCount(8)
        self._holdings_table.setHorizontalHeaderLabels(
            ["Symbol", "Name", "Shares", "Avg Cost", "Last Price",
             "Market Value", "Unrealized P/L", "Weight"]
        )
        self._holdings_table.horizontalHeader().setStretchLastSection(True)
        self._holdings_table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )
        self._holdings_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._holdings_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._holdings_table.verticalHeader().setVisible(False)
        self._holdings_table.setAlternatingRowColors(True)
        self._holdings_stack.addWidget(self._holdings_table)
        self._holdings_stack.addWidget(
            self._empty_panel("No holdings yet. Add transactions to build this portfolio.")
        )
        body.addWidget(self._holdings_stack)

        # --- Income & dividends (income sleeve) ---
        body.addWidget(_section_label("Income & Dividends"))

        income_tiles = QtWidgets.QHBoxLayout()
        income_tiles.setSpacing(12)
        self._tile_ttm_income = _MetricTile("Income (TTM)")
        self._tile_total_income = _MetricTile("Income (All-Time)")
        self._tile_yoc = _MetricTile("Yield on Cost")
        self._tile_payments = _MetricTile("Payments")
        for tile in (
            self._tile_ttm_income,
            self._tile_total_income,
            self._tile_yoc,
            self._tile_payments,
        ):
            income_tiles.addWidget(tile)
        body.addLayout(income_tiles)

        self._income_stack = QtWidgets.QStackedWidget()
        self._income_table = QtWidgets.QTableWidget()
        self._income_table.setColumnCount(7)
        self._income_table.setHorizontalHeaderLabels(
            ["Symbol", "Pay Date", "Shares", "$/Share", "Gross", "Net", "DRIP"]
        )
        self._income_table.horizontalHeader().setStretchLastSection(True)
        self._income_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._income_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._income_table.verticalHeader().setVisible(False)
        self._income_table.setAlternatingRowColors(True)
        self._income_stack.addWidget(self._income_table)
        self._income_stack.addWidget(
            self._empty_panel("No dividend income recorded yet.")
        )
        body.addWidget(self._income_stack)

        # --- Two-column: optimization + risk metrics ---
        columns = QtWidgets.QHBoxLayout()
        columns.setSpacing(18)

        opt_col = QtWidgets.QVBoxLayout()
        opt_col.setSpacing(8)
        opt_col.addWidget(_section_label("Latest Optimization & Rebalancing"))
        self._opt_stack = QtWidgets.QStackedWidget()
        self._opt_container = self._build_optimization_panel()
        self._opt_stack.addWidget(self._opt_container)
        self._opt_stack.addWidget(
            self._empty_panel("No optimization runs yet.")
        )
        opt_col.addWidget(self._opt_stack)
        columns.addLayout(opt_col, stretch=1)

        risk_col = QtWidgets.QVBoxLayout()
        risk_col.setSpacing(8)
        risk_col.addWidget(_section_label("Risk Metrics"))
        self._risk_stack = QtWidgets.QStackedWidget()
        self._risk_container = self._build_risk_panel()
        self._risk_stack.addWidget(self._risk_container)
        self._risk_stack.addWidget(self._empty_panel("No risk metrics yet."))
        risk_col.addWidget(self._risk_stack)
        columns.addLayout(risk_col, stretch=1)

        body.addLayout(columns)
        body.addStretch()

    # ---- panel builders ----

    @staticmethod
    def _empty_panel(message: str) -> QtWidgets.QWidget:
        panel = QtWidgets.QFrame()
        panel.setObjectName("Panel")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(20, 28, 20, 28)
        label = QtWidgets.QLabel(message)
        label.setObjectName("EmptyText")
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)
        return panel

    def _build_optimization_panel(self) -> QtWidgets.QFrame:
        panel = QtWidgets.QFrame()
        panel.setObjectName("Panel")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        self._opt_summary = QtWidgets.QLabel()
        self._opt_summary.setWordWrap(True)
        layout.addWidget(self._opt_summary)

        self._opt_table = QtWidgets.QTableWidget()
        self._opt_table.setColumnCount(4)
        self._opt_table.setHorizontalHeaderLabels(
            ["Symbol", "Current", "Target", "Δ Rebalance"]
        )
        self._opt_table.horizontalHeader().setStretchLastSection(True)
        self._opt_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._opt_table.verticalHeader().setVisible(False)
        self._opt_table.setAlternatingRowColors(True)
        layout.addWidget(self._opt_table)
        return panel

    def _build_risk_panel(self) -> QtWidgets.QFrame:
        panel = QtWidgets.QFrame()
        panel.setObjectName("Panel")
        self._risk_form = QtWidgets.QFormLayout(panel)
        self._risk_form.setContentsMargins(16, 14, 16, 14)
        self._risk_form.setSpacing(10)
        self._risk_form.setLabelAlignment(QtCore.Qt.AlignRight)

        self._risk_labels = {}
        for key, caption in [
            ("volatility", "Volatility"),
            ("sharpe", "Sharpe Ratio"),
            ("sortino", "Sortino Ratio"),
            ("max_drawdown", "Max Drawdown"),
            ("var95", "VaR (95%)"),
            ("cvar95", "CVaR (95%)"),
        ]:
            value_label = QtWidgets.QLabel("—")
            value_label.setObjectName("DataValue")
            self._risk_labels[key] = value_label
            self._risk_form.addRow(caption + ":", value_label)
        return panel

    # ---- data loading ----

    def load(self, portfolio_id: int):
        """Point the view at a portfolio and populate it."""
        self._portfolio_id = portfolio_id
        self.refresh()

    def showEvent(self, event):
        # Repopulate whenever the view becomes visible. This keeps the dashboard
        # current on every entry and avoids a first-show layout glitch where the
        # scroll content could render blank until the next resize event.
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        """Reload every panel from the database for the active portfolio.

        This is the single entry point for updates — navigation (showEvent),
        data changes, and future real-time polling all route here, so it's safe
        to call as often as needed.
        """
        if self._portfolio_id is None:
            return
        portfolio = get_portfolio(self._portfolio_id)
        if portfolio is None:
            self.back_requested.emit()
            return

        # Preserve scroll position so frequent refreshes don't jump the view
        scroll_pos = self._scroll.verticalScrollBar().value()

        self._name_label.setText(portfolio["name"])
        desc = portfolio.get("description") or ""
        self._desc_label.setText(desc)
        self._desc_label.setVisible(bool(desc))

        holdings = get_holdings(self._portfolio_id)
        self._populate_holdings(holdings)  # sets self._total_cost + self._market_value
        self._populate_cash(self._portfolio_id)
        self._populate_income(self._portfolio_id)
        self._populate_optimization(
            get_latest_optimization(self._portfolio_id), holdings
        )
        self._populate_risk(get_latest_risk_metrics(self._portfolio_id))

        self._scroll.verticalScrollBar().setValue(scroll_pos)

    def _populate_holdings(self, holdings: list[dict]):
        self._tile_holdings.set_value(str(len(holdings)))

        if not holdings:
            self._holdings_stack.setCurrentIndex(1)
            self._tile_value.set_value("—")
            self._tile_pl.set_value("—", "muted")
            self._tile_return.set_value("—", "muted")
            self._total_cost = 0.0  # used by yield-on-cost in the income panel
            self._market_value = 0.0  # used by the Total Value tile
            return

        # Compute per-holding valuation. Fall back to purchase price when no
        # market price has been downloaded yet, so figures stay meaningful.
        rows = []
        total_value = 0.0
        total_cost = 0.0
        for h in holdings:
            shares = h["shares"] or 0.0
            price = h["last_price"] if h["last_price"] is not None else h["purchase_price"]
            market_value = shares * (price or 0.0)
            cost = h["cost_basis"] if h["cost_basis"] else shares * (h["purchase_price"] or 0.0)
            avg_cost = (cost / shares) if shares else 0.0
            pl = market_value - cost
            rows.append(
                {**h, "price": price, "market_value": market_value,
                 "cost": cost, "avg_cost": avg_cost, "pl": pl}
            )
            total_value += market_value
            total_cost += cost

        self._holdings_table.setRowCount(len(rows))
        for r, h in enumerate(rows):
            weight = (h["market_value"] / total_value * 100) if total_value else 0.0
            cells = [
                (h["symbol"], None, QtCore.Qt.AlignLeft),
                (h["name"] or "", None, QtCore.Qt.AlignLeft),
                (f"{h['shares']:,.4f}".rstrip("0").rstrip("."), None, QtCore.Qt.AlignRight),
                (_fmt_money(h["avg_cost"]), None, QtCore.Qt.AlignRight),
                (_fmt_money(h["price"]), None, QtCore.Qt.AlignRight),
                (_fmt_money(h["market_value"]), None, QtCore.Qt.AlignRight),
                (_fmt_money(h["pl"]), theme.pl_color(h["pl"]), QtCore.Qt.AlignRight),
                (f"{weight:.1f}%", None, QtCore.Qt.AlignRight),
            ]
            for c, (text, color, align) in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(align | QtCore.Qt.AlignVCenter)
                if color is not None:
                    item.setForeground(color)
                self._holdings_table.setItem(r, c, item)
        self._holdings_table.resizeColumnsToContents()
        self._holdings_stack.setCurrentIndex(0)

        total_pl = total_value - total_cost
        total_return = (total_pl / total_cost * 100) if total_cost else None
        self._tile_value.set_value(_fmt_money(total_value))
        self._tile_pl.set_value(_fmt_money(total_pl), theme.pl_kind(total_pl))
        self._tile_return.set_value(_fmt_pct(total_return), theme.pl_kind(total_pl))
        self._market_value = total_value  # for the Total Value tile

        # Stash for downstream panels: rebalancing comparison + yield on cost
        self._current_weights = {
            h["symbol"]: (h["market_value"] / total_value) if total_value else 0.0
            for h in rows
        }
        self._total_cost = total_cost

    def _populate_cash(self, portfolio_id: int):
        cash = get_cash_summary(portfolio_id)["balance"]
        # Only flag negative cash (margin/overdraw); a positive balance is neutral.
        self._tile_cash.set_value(_fmt_money(cash), "loss" if cash < 0 else None)
        total = getattr(self, "_market_value", 0.0) + cash
        self._tile_total.set_value(_fmt_money(total))

    def _populate_income(self, portfolio_id: int):
        summary = get_income_summary(portfolio_id)
        ttm = summary["ttm_income"]
        total = summary["total_income"]
        count = summary["payment_count"]

        self._tile_ttm_income.set_value(
            _fmt_money(ttm), "gain" if ttm else "muted"
        )
        self._tile_total_income.set_value(
            _fmt_money(total), "gain" if total else "muted"
        )
        # Yield on cost = trailing-12-month income / total cost basis
        total_cost = getattr(self, "_total_cost", 0.0)
        if total_cost:
            self._tile_yoc.set_value(f"{ttm / total_cost * 100:.2f}%", "gain" if ttm else "muted")
        else:
            self._tile_yoc.set_value("—", "muted")
        self._tile_payments.set_value(str(count))

        payments = get_dividend_income(portfolio_id)
        if not payments:
            self._income_stack.setCurrentIndex(1)
            return

        self._income_table.setRowCount(len(payments))
        for r, p in enumerate(payments):
            cells = [
                (p["symbol"], None, QtCore.Qt.AlignLeft),
                (str(p["pay_date"]), None, QtCore.Qt.AlignLeft),
                (f"{p['shares_held']:,.4f}".rstrip("0").rstrip("."), None, QtCore.Qt.AlignRight),
                (_fmt_money(p["amount_per_share"]), None, QtCore.Qt.AlignRight),
                (_fmt_money(p["gross_amount"]), None, QtCore.Qt.AlignRight),
                (_fmt_money(p["net_amount"]), theme.gain(), QtCore.Qt.AlignRight),
                ("Yes" if p["is_reinvested"] else "—", None, QtCore.Qt.AlignCenter),
            ]
            for c, (text, color, align) in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(align | QtCore.Qt.AlignVCenter)
                if color is not None:
                    item.setForeground(color)
                self._income_table.setItem(r, c, item)
        self._income_table.resizeColumnsToContents()
        self._income_table.horizontalHeader().setStretchLastSection(True)
        self._income_stack.setCurrentIndex(0)

    def _populate_optimization(self, opt: dict | None, holdings: list[dict]):
        if not opt:
            self._opt_stack.setCurrentIndex(1)
            return

        run = opt["run"]
        self._opt_summary.setText(
            f"<b>{run['algorithm']}</b> &nbsp;·&nbsp; "
            f"Expected return {run['expected_return']:.2%} &nbsp;·&nbsp; "
            f"Volatility {run['expected_volatility']:.2%} &nbsp;·&nbsp; "
            f"Sharpe {run['sharpe_ratio']:.2f}<br>"
            f"<span style='color:{theme.text_muted_hex()}'>Run {run['created_at']}</span>"
        )

        current_weights = getattr(self, "_current_weights", {})
        allocations = opt["allocations"]
        self._opt_table.setRowCount(len(allocations))
        for r, alloc in enumerate(allocations):
            symbol = alloc["symbol"]
            target = alloc["recommended_weight"] or 0.0
            current = current_weights.get(symbol, 0.0)
            delta = target - current
            cells = [
                (symbol, None, QtCore.Qt.AlignLeft),
                (f"{current * 100:.1f}%", None, QtCore.Qt.AlignRight),
                (f"{target * 100:.1f}%", None, QtCore.Qt.AlignRight),
                (f"{delta * 100:+.1f}%", theme.pl_color(delta), QtCore.Qt.AlignRight),
            ]
            for c, (text, color, align) in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setTextAlignment(align | QtCore.Qt.AlignVCenter)
                if color is not None:
                    item.setForeground(color)
                self._opt_table.setItem(r, c, item)
        self._opt_table.resizeColumnsToContents()
        self._opt_table.horizontalHeader().setStretchLastSection(True)
        self._opt_stack.setCurrentIndex(0)

    def _populate_risk(self, metrics: dict | None):
        if not metrics:
            self._risk_stack.setCurrentIndex(1)
            return
        self._risk_labels["volatility"].setText(f"{metrics['volatility']:.2%}")
        self._risk_labels["sharpe"].setText(f"{metrics['sharpe']:.2f}")
        self._risk_labels["sortino"].setText(f"{metrics['sortino']:.2f}")
        self._risk_labels["max_drawdown"].setText(f"{metrics['max_drawdown']:.2%}")
        self._risk_labels["var95"].setText(f"{metrics['var95']:.2%}")
        self._risk_labels["cvar95"].setText(f"{metrics['cvar95']:.2%}")
        self._risk_stack.setCurrentIndex(0)
