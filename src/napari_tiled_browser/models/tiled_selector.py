import json
import logging
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from math import ceil
from urllib.parse import ParseResult
from urllib.parse import urlparse as _urlparse

from httpx import ConnectError
from qtpy.QtCore import QObject, Signal
from tiled.client import from_uri
from tiled.client.array import ArrayClient
from tiled.client.base import BaseClient
from tiled.queries import FullText, Key, Regex
from tiled.structures.core import StructureFamily

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


class TiledSelectorSignals(QObject):
    """Collection of signals for a TiledSelector model."""

    client_connected = Signal(
        str,  # new URL
        str,  # new API URL
        name="TiledSelector.client_connected",
    )
    client_connection_error = Signal(
        str,  # Error message
        name="TiledSelector.client_connection_error",
    )
    plottable_image_data_received = Signal(
        ArrayClient,  # node
        str,  # child_node_path
        name="TiledSelector.plottable_image_data_received",
    )
    table_changed = Signal(
        tuple,  # New node path parts, tuple of strings
        name="TiledSelector.table_changed",
    )
    url_changed = Signal(
        name="TiledSelector.url_changed",
    )
    url_validation_error = Signal(
        str,  # Error message
        name="TiledSelector.url_validation_error",
    )

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)


class TiledSelector:
    """View Model for selecting a Tiled CatalogOfBlueskyRuns."""

    Signals = TiledSelectorSignals
    SUPPORTED_TYPES = (StructureFamily.array, StructureFamily.container)

    def __init__(
        self,
        /,
        url: str = "",
        client: BaseClient = None,
        validators: Mapping[str, list[Callable]] = None,
        parent: QObject | None = None,
        rows_per_page_options: list[int] | None = None,
        *args,
        **kwargs,
    ):
        _logger.debug("TiledSelector.__init__()...")

        self._url = url
        self._client = client
        self.validators = defaultdict(list)
        if validators:
            self.validators.update(validators)

        self.signals = self.Signals(parent)
        self.client_connected = self.signals.client_connected
        self.client_connection_error = self.signals.client_connection_error
        self.plottable_image_data_received = (
            self.signals.plottable_image_data_received
        )
        self.table_changed = self.signals.table_changed
        self.url_changed = self.signals.url_changed
        self.url_validation_error = self.signals.url_validation_error

        # A buffer to receive updates while the URL is being edited
        self._url_buffer = self.url

        self.node_path_parts = ()
        self._current_page = 0
        if rows_per_page_options is None:
            self._rows_per_page_options = [5, 10, 25]
        else:
            self._rows_per_page_options = rows_per_page_options
        self._rows_per_page_index = 0
        self.search_results = None

    @property
    def url(self) -> str:
        """URL for accessing tiled server data."""
        return self._url

    @url.setter
    def url(self, value: str):
        """Updates the URL (and buffer) for accessing tiled server data.

        Emits the 'url_changed' signal.
        """
        old_value = self._url
        self._url = value
        self._url_buffer = value
        if value != old_value:
            self.url_changed.emit()

    @property
    def client(self):
        """Fetch the root Tiled client."""
        return self._client

    @client.setter
    def client(self, _):
        """Do not directly replace the root Tiled client."""
        raise NotImplementedError("Call connect_client() instead")

    @property
    def rows_per_page(self):
        return self._rows_per_page_options[self._rows_per_page_index]

    @property
    def node_len(self):
        """Convenience function for returning total length of node/search result."""
        if self.search_results is None:
            return len(self.get_current_node())
        else:
            return len(self.search_results)

    def on_url_text_edited(self, new_text: str):
        """Handle a notification that the URL is being edited."""
        _logger.debug("TiledSelector.on_url_text_edited()...")

        self._url_buffer = new_text

    def on_url_editing_finished(self):
        """Handle a notification that URL editing is complete."""
        _logger.debug("TiledSelector.on_url_editing_finished()...")

        new_url = self._url_buffer.strip()

        try:
            for validate in self.validators["url"]:
                validate(new_url)
        except ValueError as exception:
            error_message = str(exception)
            _logger.error(error_message)
            self.url_validation_error.emit(error_message)
            return

        self.url = new_url

    def on_connect_clicked(self, checked: bool = False):
        """Handle a button click to connect to the Tiled client."""
        _logger.debug("TiledSelector.on_connect_clicked()...")

        if self.client:
            # TODO: Clean-up previously connected client?
            ...

        self.connect_client()
        self.reset_client_view()

    def connect_client(self) -> None:
        """Connect the model's Tiled client to the Tiled server at URL.

        Emits the 'client_connection_error' signal when client does not connect.
        """
        try:
            new_client = self.client_from_url(self.url)
        except ConnectError as exception:
            error_message = str(exception)
            _logger.error(error_message)
            self.client_connection_error.emit(error_message)
            return

        self._client = new_client
        self.client_connected.emit(
            self._client.uri, str(self._client.context.api_uri)
        )

    def reset_client_view(self) -> None:
        """Prepare the model to receive content from a Tiled server.

        Emits the 'table_changed' signal when a client is defined.
        """
        self.node_path_parts = ()
        self._current_page = 0
        if self.client is not None:
            self.table_changed.emit(self.node_path_parts)

    # def is_catalog_of_bluesky_runs(self, node):
    #     specs = node.item["attributes"]["specs"]
    #     for spec in specs:
    #         if spec["name"] == "CatalogOfBlueskyRuns":
    #             return True
    #         else:
    #             pass
    #     return False

    def on_item_selected(self, child_node_path):
        node_path_parts = self.node_path_parts + (child_node_path,)
        # node_offset = self.rows_per_page * self._current_page
        node = self.get_parent_node(node_path_parts)

        # if self.is_catalog_of_bluesky_runs(node):
        #     self.load_button_enabled = True
        # else:
        #     self.load_button_enabled = False

        attrs = node.item["attributes"]
        family = attrs["structure_family"]
        metadata = json.dumps(attrs["metadata"], indent=2, default=json_decode)

        info = f"<b>type:</b> {family}<br>"
        if family == StructureFamily.array:
            shape = attrs["structure"]["shape"]
            info += f"<b>shape:</b> {tuple(shape)}<br>"
        info += f"<b>metadata:</b> {metadata}"
        self.info_text = info

        if family in self.SUPPORTED_TYPES:
            self.load_button_enabled = True
        else:
            self.load_button_enabled = False

    # def open_catalog(self, child_node_path):
    #     self.selected_catalog_path = self.node_path_parts + (child_node_path,)

    def on_rows_per_page_changed(self, index):
        self._rows_per_page_index = index
        self._current_page = 0
        self.table_changed.emit(self.node_path_parts)

    def on_first_page_clicked(self):
        self._current_page = 0
        self.table_changed.emit(self.node_path_parts)

    def on_prev_page_clicked(self):
        if self._current_page != 0:
            self._current_page -= 1
            self.table_changed.emit(self.node_path_parts)

    def on_next_page_clicked(self):
        rows_per_page = self.rows_per_page
        if (
            self._current_page * rows_per_page
        ) + rows_per_page < self.node_len:
            self._current_page += 1
            self.table_changed.emit(self.node_path_parts)

    def on_last_page_clicked(self):
        # NOTE: math.ceil gives the wrong answer for really large numbers
        # Solution 4 in this answer: https://stackoverflow.com/a/54585138
        self._current_page = ceil(self.node_len / self.rows_per_page) - 1
        self.table_changed.emit(self.node_path_parts)

    def get_current_node(self) -> BaseClient:
        """Fetch a Tiled client corresponding to the current node path."""
        # node_offset = self.rows_per_page * self._current_page
        return self.get_parent_node(self.node_path_parts)

    def get_parent_node(self, node_path_parts: tuple[str]) -> list:
        """Fetch a node from Tiled corresponding to the node path."""
        _logger.debug("TiledSelector.get_parent_node(%s)...", node_path_parts)
        # NOTE: Passing tiled a tuple returns a list of bluesky runs
        # even if there is only one item in the tuple
        # This may change in the future when the capability to pass a list
        # of uids to tiled is removed
        client = self.client
        # Walk down one node at a time (slow, but safe).
        for segment in node_path_parts:
            client = client[segment]

        return client

    # @functools.lru_cache(maxsize=1)
    def get_node(self, node_path_parts: tuple[str], node_offset: int) -> list:
        """Fetch a chunk of Tiled data corresponding to the node path."""
        # NOTE: Passing tiled a tuple returns a list of bluesky runs
        # even if there is only one item in the tuple
        # This may change in the future when the capability to pass a list
        # of uids to tiled is removed
        if node_path_parts:
            return self.client[node_path_parts[0]].values()[
                node_offset : node_offset + self.rows_per_page
            ]

        # An empty tuple indicates the root node
        return self.client.values()[
            node_offset : node_offset + self.rows_per_page
        ]

    def enter_node(self, child_node_path: str) -> None:
        """Select a child node within the current Tiled node.

        Emits the 'table_changed' signal."""
        _logger.info("Entering node...")
        self.node_path_parts += (child_node_path,)
        self._current_page = 0
        self.table_changed.emit(self.node_path_parts)

    def exit_node(self) -> None:
        """Select parent Tiled node.

        Emits the 'table_changed' signal."""
        _logger.info("Exiting node...")
        self.node_path_parts = self.node_path_parts[:-1]
        self._current_page = 0
        self.table_changed.emit(self.node_path_parts)

    def jump_to_node(self, index) -> None:
        """Select parent Tiled node.

        Emits the 'table_changed' signal."""
        _logger.info("Jumping to node at index %d...", index)
        self.node_path_parts = self.node_path_parts[:index]
        self._current_page = 0
        self.table_changed.emit(self.node_path_parts)

    def open_node(self, child_node_path: str) -> None:
        """Select a child node if its Tiled structure_family is supported."""
        node = self.get_current_node()[child_node_path]
        _logger.debug("New node: %s", node.uri)
        family = node.item["attributes"]["structure_family"]

        if family == StructureFamily.array:
            _logger.info("  Found array, plotting")
            self.plottable_image_data_received.emit(node, child_node_path)
        elif family == StructureFamily.container:
            _logger.debug("Entering container: %s", child_node_path)
            self.enter_node(child_node_path)
        else:
            _logger.info("StructureFamily not supported: %s", family)
            # TODO: Emit an error signal for dialog widget to respond to

    def search(self, key, value, search_type):
        """Perform Tiled search."""
        if self.node_path_parts:
            _client = self.client[self.node_path_parts]
        else:
            _client = self.client
        if search_type == "key_value":
            results = _client.search(Key(key) == value)
        elif search_type == "full_text":
            results = _client.search(FullText(value))
        elif search_type == "regex":
            results = _client.search(Regex(key, pattern=value))
        else:
            _logger.info("Unknown search type %s. Returning...", search_type)
            results = None
        self.search_results = results
        self.table_changed.emit(self.node_path_parts)

    @staticmethod
    def client_from_url(url: str):
        """Create a Tiled client that is connected to the requested URL."""
        _logger.debug("TiledSelector.client_from_url()...")

        return from_uri(url)


def urlparse(url: str) -> ParseResult:
    """Re-raise URL parsing errors with an extra custom message."""
    try:
        url_parts = _urlparse(url)
    except ValueError as exception:
        raise ValueError(f"{url} is not a valid URL.") from exception

    if not url_parts.scheme:
        raise ValueError(
            f"{url} is not a valid URL. URL must include a scheme."
        )

    if not url_parts.netloc:
        raise ValueError(
            f"{url} is not a valid URL. URL must include a network location."
        )

    return url_parts


def validate_url_syntax(url: str) -> None:
    """Verify that input string is parseable as a URL."""
    urlparse(url)


def validate_url_scheme(
    url: str,
    valid_schemes: Sequence[str] = ("http", "https"),
) -> None:
    """Verify that URL scheme is one of 'valid_schemes'."""
    url_parts = urlparse(url)

    if url_parts.scheme not in valid_schemes:
        error_message = " ".join(
            (
                f"{url} is not a valid Tiled URL.",
                "URL must start with",
                " or ".join(valid_schemes),
                ".",
            )
        )
        raise ValueError(error_message)
