"""
This module is an example of a barebones QWidget plugin for napari

It implements the Widget specification.
see: https://napari.org/plugins/guides.html?#widgets

Replace code below according to your needs.
"""

import collections
import logging
from datetime import date, datetime

from napari.resources._icons import ICONS
from qtpy.QtCore import Qt, QThreadPool, Signal
from qtpy.QtGui import QIcon, QPixmap
from qtpy.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from tiled.client.array import DaskArrayClient
from tiled.client.container import Container
from tiled.structures.core import StructureFamily

from napari_tiled_browser.models.tiled_selector import TiledSelector
from napari_tiled_browser.models.tiled_worker import TiledWorker
from napari_tiled_browser.models.tiled_subscriber import TiledSubscriber
from napari_tiled_browser.qt.tiled_search import QTiledSearchWidget

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)

console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
    datefmt="%m-%d %H:%M:%S",
)
console.setFormatter(formatter)
_logger.addHandler(console)


def json_decode(obj):
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    return str(obj)


class DummyClient:
    "Placeholder for a structure family we cannot (yet) handle"

    def __init__(self, *args, item, **kwargs):
        self.item = item


STRUCTURE_CLIENTS = collections.defaultdict(lambda: DummyClient)
STRUCTURE_CLIENTS.update({"array": DaskArrayClient, "container": Container})


class QTiledBrowser(QWidget):
    NODE_ID_MAXLEN = 8

    # your QWidget.__init__ can optionally request the napari viewer instance
    # in one of two ways:
    # 1. use a parameter called `napari_viewer`, as done here
    # 2. use a type annotation of 'napari.viewer.Viewer' for any parameter
    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer

        # TODO: try using TILED_DEFAULT_PROFILE here?
        self.model = TiledSelector()

        self.thread_pool = QThreadPool.globalInstance()

        self.create_layout()
        self.connect_model_signals()
        self.connect_model_slots()
        self.connect_self_signals()
        self.initialize_values()

    def create_layout(self):
        # Connection elements
        self.url_entry = QLineEdit()
        self.connect_button = QPushButton("Connect")
        self.connection_label = QLabel("No url connected")
        self.connection_widget = QWidget()

        # Connection layout
        connection_layout = QVBoxLayout()
        connection_layout.addWidget(self.url_entry)
        connection_layout.addWidget(self.connect_button)
        connection_layout.addWidget(self.connection_label)
        connection_layout.addStretch()
        self.connection_widget.setLayout(connection_layout)

        # Search widget
        self.search_widget = QTiledSearchWidget(model=self.model)
        self.search_widget.setVisible(False)

        # Navigation elements
        self.rows_per_page_label = QLabel("Rows per page: ")
        self.rows_per_page_selector = QComboBox()

        self.current_location_label = QLabel()
        self.first_page = ClickableQLabel("<<")
        self.previous_page = ClickableQLabel("<")
        self.next_page = ClickableQLabel(">")
        self.last_page = ClickableQLabel(">>")
        self.navigation_widget = QWidget()

        # Navigation layout
        navigation_layout = QHBoxLayout()
        navigation_layout.addWidget(self.rows_per_page_label)
        navigation_layout.addWidget(self.rows_per_page_selector)
        navigation_layout.addWidget(self.current_location_label)
        navigation_layout.addWidget(self.first_page)
        navigation_layout.addWidget(self.previous_page)
        navigation_layout.addWidget(self.next_page)
        navigation_layout.addWidget(self.last_page)
        self.navigation_widget.setLayout(navigation_layout)

        # Current path layout
        self.current_path_widget = QWidget()
        self.current_path_layout = QHBoxLayout()
        self.current_path_layout.setAlignment(Qt.AlignLeft)
        self.current_path_widget.setLayout(self.current_path_layout)
        self._rebuild_current_path_layout()

        # Catalog table elements
        self.catalog_table = QTableWidget(0, 1)
        self.catalog_table.horizontalHeader().setStretchLastSection(True)
        self.catalog_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )  # disable editing
        self.catalog_table.horizontalHeader().hide()  # remove header
        self.catalog_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )  # disable multi-select
        self.catalog_table_widget = QWidget()
        self.catalog_breadcrumbs = None

        # Info layout
        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)
        self.load_button = QPushButton("Open")
        self.load_button.setEnabled(False)
        catalog_info_layout = QHBoxLayout()
        catalog_info_layout.addWidget(self.catalog_table)
        load_layout = QVBoxLayout()
        load_layout.addWidget(self.info_box)
        load_layout.addWidget(self.load_button)
        catalog_info_layout.addLayout(load_layout)

        # Catalog table layout
        catalog_table_layout = QVBoxLayout()
        catalog_table_layout.addWidget(self.current_path_widget)
        catalog_table_layout.addLayout(catalog_info_layout)
        catalog_table_layout.addWidget(self.navigation_widget)
        catalog_table_layout.addStretch(1)
        self.catalog_table_widget.setLayout(catalog_table_layout)
        self.catalog_table_widget.setVisible(False)

        self.splitter = QSplitter(self)
        self.splitter.setOrientation(Qt.Orientation.Vertical)

        self.splitter.addWidget(self.connection_widget)
        self.splitter.addWidget(self.search_widget)
        self.splitter.addWidget(self.catalog_table_widget)

        self.splitter.setStretchFactor(2, 2)

        layout = QVBoxLayout()
        layout.addWidget(self.splitter)
        self.setLayout(layout)

    def reset_url_entry(self) -> None:
        """Reset the state of the url_entry widget."""
        _logger.debug("QTiledBrowser.reset_url_entry()...")

        if not self.model.url:
            self.url_entry.setPlaceholderText("Enter a url")
        else:
            self.url_entry.setText(self.model.url)

    def _rebuild_current_path_layout(self):
        """Reset the clickable widgets for the current path breadcrumbs."""
        _logger.debug("QTiledBrowser._rebuild_current_path_layout()...")
        bc_widget = ClickableIndexedQLabel("root", index=0)
        bc_widget.setObjectName("root")
        bc_widget.clicked.connect(self._on_breadcrumb_clicked)
        breadcrumbs = [bc_widget]

        for i, node_id in enumerate(self.model.node_path_parts, start=1):
            if len(node_id) > self.NODE_ID_MAXLEN:
                short_node_id = node_id[: self.NODE_ID_MAXLEN - 3] + "..."
                bc_widget = ClickableIndexedQLabel(short_node_id, index=i)
            else:
                bc_widget = ClickableIndexedQLabel(node_id, index=i)

            bc_widget.setObjectName(node_id)
            bc_widget.clicked.connect(self._on_breadcrumb_clicked)
            breadcrumbs.append(bc_widget)

        # remove all widgets from current_path_layout
        self.remove_current_path_layout_widgets()

        for breadcrumb in breadcrumbs:
            self.current_path_layout.addWidget(breadcrumb)
            self.current_path_layout.addWidget(QLabel(" / "))

    def remove_current_path_layout_widgets(self):
        """Remove unneeded path widgets and free the memory."""
        for index in reversed(range(self.current_path_layout.count())):
            widget = self.current_path_layout.itemAt(index).widget()
            self.current_path_layout.removeWidget(widget)
            widget.deleteLater()

    def reset_rows_per_page(self) -> None:
        """Reset the state of the rows_per_page_selector widget."""
        _logger.debug("QTiledWidget.reset_rows_per_page()...")

        self.rows_per_page_selector.addItems(
            [str(option) for option in self.model._rows_per_page_options]
        )
        self.rows_per_page_selector.setCurrentIndex(
            self.model._rows_per_page_index
        )

    def fetch_table_data(self):
        runnable = TiledWorker(
            rows_per_page=self.model.rows_per_page,
            current_page=self.model._current_page,
            client=self.model.client,
            search_results=self.model.search_results,
            node_path_parts=self.model.node_path_parts,
        )
        runnable.signals.results.connect(self.populate_table)
        self.thread_pool.start(runnable)

    def subscribe_to_table_data(self):
        catalog = self.model.client[self.model.node_path_parts]
        runnable = TiledSubscriber(catalog)
        self.thread_pool.start(runnable)

    def populate_table(self, results):
        _logger.debug("QTiledBrowser.populate_table()...")
        original_state = {}
        self.search_widget.setVisible(True)
        self.catalog_table_widget.setVisible(True)

        original_state["blockSignals"] = self.catalog_table.blockSignals(True)

        # Remove all rows first
        while self.catalog_table.rowCount() > 0:
            self.catalog_table.removeRow(0)

        if self.model.node_path_parts:
            # add breadcrumbs
            self.catalog_breadcrumbs = QTableWidgetItem("..")
            self.catalog_table.insertRow(0)
            self.catalog_table.setItem(0, 0, self.catalog_breadcrumbs)

        # Then add new rows
        rows_per_page = self.model.rows_per_page
        for _ in range(rows_per_page):
            last_row_position = self.catalog_table.rowCount()
            self.catalog_table.insertRow(last_row_position)
        node_offset = rows_per_page * self.model._current_page

        items = results
        # Loop over rows, filling in keys until we run out of keys.
        start = 1 if self.model.node_path_parts else 0
        for row_index, (key, value) in zip(
            range(start, self.catalog_table.rowCount()), items, strict=False
        ):
            family = value.item["attributes"]["structure_family"]
            # TODO: make this dictionary with StructureFamily type as key
            # and action for StructureFamily as value
            if family == StructureFamily.container:
                icon = self.style().standardIcon(QStyle.SP_DirHomeIcon)
            elif family == StructureFamily.array:
                icon = QIcon(QPixmap(ICONS["new_image"]))
            else:
                icon = self.style().standardIcon(
                    QStyle.SP_TitleBarContextHelpButton
                )
            self.catalog_table.setItem(
                row_index, 0, QTableWidgetItem(icon, key)
            )

        # remove extra rows
        for _ in range(self.model.rows_per_page - len(items)):
            self.catalog_table.removeRow(self.catalog_table.rowCount() - 1)

        headers = [
            str(x + 1)
            for x in range(
                node_offset, node_offset + self.catalog_table.rowCount()
            )
        ]
        if self.model.node_path_parts:
            headers = [""] + headers

        self.catalog_table.setVerticalHeaderLabels(headers)
        self._clear_metadata()
        self.catalog_table.blockSignals(original_state["blockSignals"])
        self._set_current_location_label()

    def connect_model_signals(self):
        """Connect dialog slots to model signals."""
        _logger.debug("QTiledBrowser.connect_model_signals()...")

        @self.model.client_connected.connect
        def on_client_connected(url: str, api_url: str):
            self.connection_label.setText(f"Connected to {url}")
            # TODO: Display the contents of the Tiled node

        @self.model.client_connection_error.connect
        def on_client_connection_error(error_msg: str):
            # TODO: Display the error message; suggest a remedy
            ...

        @self.model.table_changed.connect
        def on_table_changed(node_path_parts: tuple[str]):
            _logger.debug("on_table_changed(): %s", node_path_parts)
            if self.model.client is None:
                # TODO: handle disconnecting from tiled client later
                return
            # self._set_current_location_label()
            self.fetch_table_data()
            self.subscribe_to_table_data()
            self._rebuild_current_path_layout()

        self.model.url_changed.connect(self.reset_url_entry)

        @self.model.plottable_data_received.connect
        def on_plottable_data_received(node, child_node_path):
            layer = self.viewer.add_image(node, name=child_node_path)
            layer.reset_contrast_limits()

    def connect_model_slots(self):
        """Connect model slots to dialog signals."""
        _logger.debug("QTiledBrowser.connect_model_slots()...")

        self.url_entry.textEdited.connect(self.model.on_url_text_edited)
        self.url_entry.editingFinished.connect(
            self.model.on_url_editing_finished
        )
        self.connect_button.clicked.connect(self.model.on_connect_clicked)
        self.first_page.clicked.connect(self.model.on_first_page_clicked)
        self.next_page.clicked.connect(self.model.on_next_page_clicked)
        self.previous_page.clicked.connect(self.model.on_prev_page_clicked)
        self.last_page.clicked.connect(self.model.on_last_page_clicked)
        self.rows_per_page_selector.currentIndexChanged.connect(
            self.model.on_rows_per_page_changed
        )

    def connect_self_signals(self):
        self.load_button.clicked.connect(self._on_load)

        # self.catalog_table.itemDoubleClicked.connect(
        #     self._on_item_double_click
        # )
        self.catalog_table.itemSelectionChanged.connect(self._on_item_selected)

    def initialize_values(self):
        self.reset_url_entry()
        self.reset_rows_per_page()

    # def open_node(self, node_id):
    #     node = self.get_current_node()[node_id]
    #     family = node.item["attributes"]["structure_family"]
    #     # TODO: make this dictionary with StructureFamily type as key
    #     # and action for StructureFamily as value
    #     if isinstance(node, DummyClient):
    #         show_info(f"Cannot open type: '{family}'")
    #         return
    #     if family == StructureFamily.array:
    #         layer = self.viewer.add_image(node, name=node_id)
    #         layer.reset_contrast_limits()
    #     elif family == StructureFamily.container:
    #         self.enter_node(node_id)
    #     else:
    #         show_info(f"Type not supported:'{family}")

    def _on_load(self):
        selected = self.catalog_table.selectedItems()
        if not selected:
            return
        item = selected[0]
        if item is self.catalog_breadcrumbs:
            self.model.exit_node()
            return
        self.model.open_node(item.text())

    def _on_breadcrumb_clicked(self, node_index):
        self.model.jump_to_node(node_index)

    # def _on_item_double_click(self, item):
    #     if item is self.catalog_breadcrumbs:
    #         self.exit_node()
    #         return
    #     self.open_node(item.text())

    def _on_item_selected(self):
        selected = self.catalog_table.selectedItems()
        if not selected or (item := selected[0]) is self.catalog_breadcrumbs:
            self._clear_metadata()
            return

        child_node_path = item.text()
        self.model.on_item_selected(child_node_path)

        self.info_box.setText(self.model.info_text)
        self.load_button.setEnabled(self.model.load_button_enabled)

    def _clear_metadata(self):
        self.info_box.setText("")
        # self.load_button.setEnabled(False)

    def _set_current_location_label(self):
        _logger.debug("QTiledBrowser._set_current_location_label()...")
        starting_index = (
            self.model._current_page * self.model.rows_per_page + 1
        )
        ending_index = min(
            self.model.rows_per_page * (self.model._current_page + 1),
            self.model.node_len,
        )
        current_location_text = (
            f"{starting_index}-{ending_index} of {self.model.node_len}"
        )
        self.current_location_label.setText(current_location_text)


class ClickableQLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        self.click()

    def click(self):
        self.clicked.emit()


class ClickableIndexedQLabel(ClickableQLabel):
    clicked = Signal(int)

    def __init__(self, text, index):
        super().__init__(text)
        self.index = index

    def mousePressEvent(self, event):
        self.click()

    def click(self):
        self.clicked.emit(self.index)
