import logging

from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QLabel,
    QLineEdit,
    QWidget,
)

from napari_tiled_browser.models.tiled_selector import TiledSelector

_logger = logging.getLogger(__name__)


class QTiledSearchWidget(QWidget):
    def __init__(
        self,
        model: TiledSelector,
        parent: QWidget | None = None,
        *args,
        **kwargs,
    ) -> None:
        """Initialize."""
        _logger.debug("QTiledSearchWidget.__init__()")

        super().__init__(parent, *args, **kwargs)
        self.model = model

        self.key_label = QLabel("Key")
        self.key_entry = QLineEdit()
        self.key_entry.setClearButtonEnabled(True)
        self.value_label = QLabel("Value")
        self.value_entry = QLineEdit()
        self.value_entry.setClearButtonEnabled(True)
        self.full_text_checkbox = QCheckBox("Full text search")
        self.regex_checkbox = QCheckBox("Use RegEx pattern")
        self.full_text_hint = QLabel("Whole words only")
        self.full_text_hint.setVisible(False)

        layout = QGridLayout()
        # widget, row, column
        layout.addWidget(self.key_label, 0, 0)
        layout.addWidget(self.key_entry, 0, 1)
        layout.addWidget(self.value_label, 0, 2)
        layout.addWidget(self.value_entry, 0, 3)
        # widget, row, column, row span, column span
        layout.addWidget(self.full_text_checkbox, 1, 0, 1, 2)
        layout.addWidget(self.regex_checkbox, 1, 2, 1, 2)
        layout.addWidget(self.full_text_hint, 1, 2, 1, 2)

        self.setLayout(layout)

        self.full_text_checkbox.clicked.connect(
            self.on_full_text_checkbox_checked
        )
        self.regex_checkbox.clicked.connect(self.on_regex_checkbox_checked)

        self.debounce = QTimer()
        self.debounce.setInterval(1000)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.debounced_search)

        self.key_entry.textChanged.connect(self.debounce.start)
        self.value_entry.textChanged.connect(self.debounce.start)

    def _search(self):
        key = self.key_entry.text()
        _logger.debug("Key: %s", key)
        value = self.value_entry.text()
        _logger.debug("Value: %s", value)
        _logger.debug("Searching...")
        full_text_enabled = self.full_text_checkbox.isChecked()
        regex_enabled = self.regex_checkbox.isChecked()
        # FullText search - full text check and non empty value
        if value != "" and full_text_enabled:
            search_type = "full_text"
            key = None
        # RegEx search - regex check and non empty key and value
        elif (key != "" and value != "") and regex_enabled:
            search_type = "regex"
        # key value search - no checks and non empty key and value
        elif (key != "" and value != "") and not (
            full_text_enabled or regex_enabled
        ):
            search_type = "key_value"
        # every other combo should not search
        else:
            search_type = "no_search"
        self.model.search(key, value, search_type)
        return search_type

    def debounced_search(self):
        self._search()

    def on_full_text_checkbox_checked(self):
        self.regex_checkbox.setVisible(not self.regex_checkbox.isVisible())
        self.full_text_hint.setVisible(not self.full_text_hint.isVisible())
        self.key_label.setEnabled(not self.key_label.isEnabled())
        self.key_entry.setEnabled(not self.key_entry.isEnabled())
        self._search()

    def on_regex_checkbox_checked(self):
        self.full_text_checkbox.setEnabled(
            not self.full_text_checkbox.isEnabled()
        )
        self._search()
