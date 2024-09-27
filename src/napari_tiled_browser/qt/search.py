from math import floor

from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class SearchResults(QWidget):
    # your QWidget.__init__ can optionally request the napari viewer instance
    # in one of two ways:
    # 1. use a parameter called `napari_viewer`, as done here
    # 2. use a type annotation of 'napari.viewer.Viewer' for any parameter
    def __init__(self, model):
        super().__init__()
        self.model = model

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
        # TODO: use model._page_limit as default option here?
        self.rows_per_page_selector.addItems(["10", "20", "50"])
        self.rows_per_page_selector.setCurrentIndex(1)

        self.current_location_label = QLabel()
        self.previous_page = ClickableQLabel("<")
        self.next_page = ClickableQLabel(">")
        self.navigation_widget = QWidget()

        self._rows_per_page = int(self.rows_per_page_selector.currentText())

        # Navigation layout
        navigation_layout = QHBoxLayout()
        navigation_layout.addWidget(self.rows_per_page_label)
        navigation_layout.addWidget(self.rows_per_page_selector)
        navigation_layout.addWidget(self.current_location_label)
        navigation_layout.addWidget(self.previous_page)
        navigation_layout.addWidget(self.next_page)
        self.navigation_widget.setLayout(navigation_layout)

        # Catalog table elements
        self.catalog_table = QTableWidget(0, 1)
        self.catalog_table.setHorizontalHeaderLabels(["ID"])
        self._create_table_rows()
        self.catalog_table_widget = QWidget()

        # Catalog table layout
        catalog_table_layout = QVBoxLayout()
        catalog_table_layout.addWidget(self.catalog_table)
        catalog_table_layout.addWidget(self.navigation_widget)
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

        self.rows_per_page_selector.currentTextChanged.connect(
            self._on_rows_per_page_changed
        )

        self.model.events.connected.connect(self._on_connected)
        self.model.events.refreshed.connect(self._on_refreshed)

        if self.model.uri != "":
            self.url_entry.setText(self.model.uri)
            self.connection_label.setText(f"Connected to {self.model.uri}")
            # Create the table if we already have a uri
            self._set_current_location_label()
            self._create_table_rows()
            self._populate_table()
            self.catalog_table_widget.setVisible(True)

    def _on_connect_clicked(self):
        url = self.url_entry.displayText()
        self.model.uri = url
        self.connection_label.setText(f"Connected to {url}")

    def _on_connected(self, event):
        self.catalog_table_widget.setVisible(True)

    def _on_refreshed(self, event):
        self._set_current_location_label()
        self._create_table_rows()
        self._populate_table()

    def _on_rows_per_page_changed(self, value):
        lower_bound, _ = self.model.range
        self.model.page_limit = int(value)
        self.model.page_number = min(
            self.model.page_number,
            floor(self.model.total_length / self.model.page_limit),
        )

    def _create_table_rows(self):
        target_length = len(self.model.results)
        while self.catalog_table.rowCount() > target_length:
            self.catalog_table.removeRow(0)
        while self.catalog_table.rowCount() < target_length:
            last_row_position = self.catalog_table.rowCount()
            self.catalog_table.insertRow(last_row_position)

    def _populate_table(self):
        for row_index, node in enumerate(self.model.results):
            self.catalog_table.setItem(row_index, 0, QTableWidgetItem(node))

    def _on_prev_page_clicked(self):
        if self.model.page_number != 0:
            self.model.page_number -= 1

    def _on_next_page_clicked(self):
        if (
            self.model.page_limit * (self.model.page_number + 1)
            < self.model.total_length
        ):
            self.model.page_number += 1

    def _set_current_location_label(self):
        start, end = self.model.range
        current_location_text = (
            f"{1 + start}-{end} of {self.model.total_length}"
        )
        self.current_location_label.setText(current_location_text)


class ClickableQLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        self.clicked.emit()
