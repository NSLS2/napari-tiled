"""
This module is an example of a barebones QWidget plugin for napari

It implements the Widget specification.
see: https://napari.org/plugins/guides.html?#widgets

Replace code below according to your needs.
"""
import collections
from datetime import date, datetime
import functools
import json

from napari.utils.notifications import show_info
from napari.resources._icons import ICONS
from qtpy.QtCore import Qt, Signal
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
from tiled.client import from_uri
from tiled.client.array import DaskArrayClient
from tiled.client.container import Container
from tiled.structures.core import StructureFamily


def json_decode(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


class DummyClient:
    "Placeholder for a structure family we cannot (yet) handle"

    def __init__(self, *args, item, **kwargs):
        self.item = item


STRUCTURE_CLIENTS = collections.defaultdict(lambda: DummyClient)
STRUCTURE_CLIENTS.update({"array": DaskArrayClient, "container": Container})


class TiledBrowser(QWidget):
    NODE_ID_MAXLEN = 8
    SUPPORTED_TYPES = (StructureFamily.array, StructureFamily.container)

    # your QWidget.__init__ can optionally request the napari viewer instance
    # in one of two ways:
    # 1. use a parameter called `napari_viewer`, as done here
    # 2. use a type annotation of 'napari.viewer.Viewer' for any parameter
    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer

        self.set_root(None)

        # Connection elements
        self.url_entry = QLineEdit()
        self.url_entry.setPlaceholderText("Enter a url")
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

        # Navigation elements
        self.rows_per_page_label = QLabel("Rows per page: ")
        self.rows_per_page_selector = QComboBox()
        self.rows_per_page_selector.addItems(["5", "10", "25"])
        self.rows_per_page_selector.setCurrentIndex(0)

        self.current_location_label = QLabel()
        self.first_page = ClickableQLabel("<<")
        self.previous_page = ClickableQLabel("<")
        self.next_page = ClickableQLabel(">")
        self.last_page = ClickableQLabel(">>")
        self.navigation_widget = QWidget()

        self._rows_per_page = int(
            self.rows_per_page_selector.currentText()
        )

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
        self.current_path_layout = QHBoxLayout()
        self.current_path_layout.setSpacing(10)
        self.current_path_layout.setAlignment(Qt.AlignLeft)
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
        # disabled due to bad colour palette:
        # self.catalog_table.setAlternatingRowColors(True)
        self.catalog_table.itemDoubleClicked.connect(
            self._on_item_double_click
        )
        self.catalog_table.itemSelectionChanged.connect(self._on_item_selected)
        self.catalog_table_widget = QWidget()
        self.catalog_breadcrumbs = None

        # Info layout
        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)
        self.load_button = QPushButton("Open")
        self.load_button.setEnabled(False)
        self.load_button.clicked.connect(self._on_load)
        catalog_info_layout = QHBoxLayout()
        catalog_info_layout.addWidget(self.catalog_table)
        load_layout = QVBoxLayout()
        load_layout.addWidget(self.info_box)
        load_layout.addWidget(self.load_button)
        catalog_info_layout.addLayout(load_layout)

        # Catalog table layout
        catalog_table_layout = QVBoxLayout()
        catalog_table_layout.addWidget(self.current_path_layout)
        catalog_table_layout.addLayout(catalog_info_layout)
        catalog_table_layout.addWidget(self.navigation_widget)
        catalog_table_layout.addStretch(1)
        self.catalog_table_widget.setLayout(catalog_table_layout)
        self.catalog_table_widget.setVisible(False)

        self.splitter = QSplitter(self)
        self.splitter.setOrientation(Qt.Orientation.Vertical)

        self.splitter.addWidget(self.connection_widget)
        self.splitter.addWidget(self.catalog_table_widget)

        self.splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout()
        layout.addWidget(self.splitter)
        self.setLayout(layout)

        self.connect_button.clicked.connect(self._on_connect_clicked)
        self.previous_page.clicked.connect(self._on_prev_page_clicked)
        self.next_page.clicked.connect(self._on_next_page_clicked)
        self.first_page.clicked.connect(self._on_first_page_clicked)
        self.last_page.clicked.connect(self._on_last_page_clicked)

        self.rows_per_page_selector.currentTextChanged.connect(
            self._on_rows_per_page_changed
        )

    def _on_connect_clicked(self):
        url = self.url_entry.displayText().strip()
        # url = "https://tiled-demo.blueskyproject.io/api"
        if not url:
            show_info("Please specify a url.")
            return
        try:
            root = from_uri(url, STRUCTURE_CLIENTS)
            if isinstance(root, DummyClient):
                show_info("Unsupported tiled type detected")
        except Exception:
            show_info("Could not connect. Please check the url.")
        else:
            self.connection_label.setText(f"Connected to {url}")
            self.set_root(root)

    def set_root(self, root):
        self.root = root
        self.node_path = ()
        self._current_page = 0
        if root is not None:
            self.catalog_table_widget.setVisible(True)
            self._rebuild()

    def get_current_node(self):
        return self.get_node(self.node_path)

    @functools.lru_cache(maxsize=1)
    def get_node(self, node_path):
        if node_path:
            return self.root[node_path]
        return self.root

    def enter_node(self, node_id):
        self.node_path += (node_id,)
        self._current_page = 0
        self._rebuild()

    def exit_node(self):
        self.node_path = self.node_path[:-1]
        self._current_page = 0
        self._rebuild()

    def open_node(self, node_id):
        node = self.get_current_node()[node_id]
        family = node.item["attributes"]["structure_family"]
        if isinstance(node, DummyClient):
            show_info(f"Cannot open type: '{family}'")
            return
        if family == StructureFamily.array:
            layer = self.viewer.add_image(node, name=node_id)
            layer.reset_contrast_limits()
        elif family == StructureFamily.container:
            self.enter_node(node_id)
        else:
            show_info(f"Type not supported:'{family}")

    def _on_load(self):
        selected = self.catalog_table.selectedItems()
        if not selected:
            return
        item = selected[0]
        if item is self.catalog_breadcrumbs:
            return
        self.open_node(item.text())

    def _on_rows_per_page_changed(self, value):
        self._rows_per_page = int(value)
        self._current_page = 0
        self._rebuild_table()
        self._set_current_location_label()

    def _on_item_double_click(self, item):
        if item is self.catalog_breadcrumbs:
            self.exit_node()
            return
        self.open_node(item.text())

    def _on_item_selected(self):
        selected = self.catalog_table.selectedItems()
        if not selected or (item := selected[0]) is self.catalog_breadcrumbs:
            self._clear_metadata()
            return

        name = item.text()
        node_path = self.node_path + (name,)
        node = self.get_node(node_path)

        attrs = node.item["attributes"]
        family = attrs["structure_family"]
        metadata = json.dumps(attrs["metadata"], indent=2, default=json_decode)

        info = f"<b>type:</b> {family}<br>"
        if family == StructureFamily.array:
            shape = attrs["structure"]["macro"]["shape"]
            info += f"<b>shape:</b> {tuple(shape)}<br>"
        info += f"<b>metadata:</b> {metadata}"
        self.info_box.setText(info)

        if family in self.SUPPORTED_TYPES:
            self.load_button.setEnabled(True)
        else:
            self.load_button.setEnabled(False)

    def _clear_metadata(self):
        self.info_box.setText("")
        self.load_button.setEnabled(False)

    def _on_breadcrumb_clicked(self, node):
        # If root is selected.
        if node == "root":
            self.node_path = ()
            self._rebuild()
        
        # For any node other than root.
        else:
            try:
                index = self.node_path.index(node)
                self.node_path = self.node_path[:index + 1]
                self._rebuild()
            
            # If node ID has been truncated.
            except ValueError:
                for i, node_id in enumerate(self.node_path):
                    if node == node_id[self.NODE_ID_MAXLEN - 3] + "...":
                        index = i
                        break

                self.node_path = self.node_path[:index + 1]
                self._rebuild

    def _clear_current_path_layout(self):
        for i in reversed(range(self.current_path_layout.count())):
            widget = self.current_path_layout.itemAt(i).widget()
            self.current_path_layout.removeWidget(widget)
            widget.deleteLater()

    def _rebuild_current_path_layout(self):
        # Add root to widget list.
        root = ClickableQLabel("root")
        root.clicked_with_text.connect(self._on_breadcrumb_clicked)
        widgets = [root]

        # Appropritaely truncate node_id.
        for node_id in self.node_path:
            if len(node_id) > self.NODE_ID_MAXLEN:
                node_id = node_id[: self.NODE_ID_MAXLEN - 3] + "..."

            # Convert node_id into a ClickableQWidget and add to widget list.
            clickable_label = ClickableQLabel(node_id)
            clickable_label.clicked_with_text.connect(self._on_breadcrumb_clicked)
            widgets.append(clickable_label)

        # Add nodes to node path.
        if len(self.current_path_layout) < len(widgets):
            for widget in widgets:
                widget = widgets[-1]
                self.current_path_layout.addWidget(widget)

        # Remove nodes from node path after they are exited.
        elif len(self.current_path_layout) > len(widgets):
            self._clear_current_path_layout()
            while len(self.current_path_layout) < len(widgets):
                for widget in widgets:
                    self.current_path_layout.addWidget(widget)

    def _rebuild_table(self):
        prev_block = self.catalog_table.blockSignals(True)
        # Remove all rows first
        while self.catalog_table.rowCount() > 0:
            self.catalog_table.removeRow(0)

        if self.node_path:
            # add breadcrumbs
            self.catalog_breadcrumbs = QTableWidgetItem("..")
            self.catalog_table.insertRow(0)
            self.catalog_table.setItem(0, 0, self.catalog_breadcrumbs)

        # Then add new rows
        for row in range(self._rows_per_page):
            last_row_position = self.catalog_table.rowCount()
            self.catalog_table.insertRow(last_row_position)
        node_offset = self._rows_per_page * self._current_page
        # Fetch a page of keys.
        items = self.get_current_node().items()[
            node_offset : node_offset + self._rows_per_page
        ]
        # Loop over rows, filling in keys until we run out of keys.
        start = 1 if self.node_path else 0
        for row_index, (key, value) in zip(
            range(start, self.catalog_table.rowCount()), items
        ):
            family = value.item["attributes"]["structure_family"]
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
        for row in range(self._rows_per_page - len(items)):
            self.catalog_table.removeRow(self.catalog_table.rowCount() - 1)

        headers = [
            str(x + 1)
            for x in range(
                node_offset, node_offset + self.catalog_table.rowCount()
            )
        ]
        if self.node_path:
            headers = [""] + headers

        self.catalog_table.setVerticalHeaderLabels(headers)
        self._clear_metadata()
        self.catalog_table.blockSignals(prev_block)

    def _rebuild(self):
        self._rebuild_table()
        self._rebuild_current_path_layout()
        self._set_current_location_label()

    def _on_prev_page_clicked(self):
        if self._current_page != 0:
            self._current_page -= 1
            self._rebuild()

    def _on_next_page_clicked(self):
        if (
            self._current_page * self._rows_per_page
        ) + self._rows_per_page < len(self.get_current_node()):
            self._current_page += 1
            self._rebuild()

    def _on_first_page_clicked(self):
        if self._current_page != 0:
            self._current_page = 0
            self._rebuild()

    def _on_last_page_clicked(self):
        while True:
            if(
                self._current_page * self._rows_per_page
            ) + self._rows_per_page < len(self.get_current_node()):
                self._current_page += 1
            else:
                self._rebuild
                break

    def _set_current_location_label(self):
        starting_index = self._current_page * self._rows_per_page + 1
        ending_index = min(
            self._rows_per_page * (self._current_page + 1),
            len(self.get_current_node()),
        )
        current_location_text = f"{starting_index}-{ending_index} of {len(self.get_current_node())}"
        self.current_location_label.setText(current_location_text)


class ClickableQLabel(QLabel):
    clicked = Signal()
    clicked_with_text = Signal(str)

    def mousePressEvent(self, event):
        self.clicked.emit()
        self.clicked_with_text.emit(self.text())


# TODO: handle changing the location label/current_page when on last page and
# increasing rows per page
