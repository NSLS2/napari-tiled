"""Login widget for Tiled authentication.

Provides a Qt-based login dialog that supports:
- API key authentication
- Username/password (internal) authentication
- Device code (external/OAuth2) authentication
"""

import logging
import webbrowser

from qtpy.QtCore import QTimer, Signal
from qtpy.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

_logger = logging.getLogger(__name__)


class QTiledLoginWidget(QWidget):
    """Widget for handling Tiled server authentication.

    Emits signals for the different authentication methods
    so the model can perform the actual authentication.
    """

    api_key_submitted = Signal(str)  # api_key
    password_submitted = Signal(str, str)  # username, password
    login_requested = Signal()
    logout_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._create_layout()

    def _create_layout(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Auth method selector
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("Auth:"))
        self.auth_method_selector = QComboBox()
        self.auth_method_selector.addItems(
            ["None", "API Key", "Password", "Device Code"]
        )
        method_layout.addWidget(self.auth_method_selector)

        # Status label
        self.status_label = QLabel("")
        method_layout.addWidget(self.status_label)
        method_layout.addStretch()
        main_layout.addLayout(method_layout)

        # Stacked widget for different auth forms
        self.auth_stack = QStackedWidget()

        # Page 0: No auth (empty)
        self.auth_stack.addWidget(QWidget())

        # Page 1: API Key
        self.auth_stack.addWidget(self._create_api_key_page())

        # Page 2: Password
        self.auth_stack.addWidget(self._create_password_page())

        # Page 3: Device Code
        self.auth_stack.addWidget(self._create_device_code_page())

        main_layout.addWidget(self.auth_stack)

        # Login / Logout buttons
        button_layout = QHBoxLayout()
        self.login_button = QPushButton("Login")
        self.logout_button = QPushButton("Logout")
        self.logout_button.setEnabled(False)
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.logout_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

        # Connections
        self.auth_method_selector.currentIndexChanged.connect(
            self.auth_stack.setCurrentIndex
        )
        self.login_button.clicked.connect(self._on_login_clicked)
        self.logout_button.clicked.connect(self._on_logout_clicked)

    def _create_api_key_page(self):
        page = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("API Key:"))
        self.api_key_entry = QLineEdit()
        self.api_key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_entry.setPlaceholderText("Enter API key")
        layout.addWidget(self.api_key_entry)
        page.setLayout(layout)
        return page

    def _create_password_page(self):
        page = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Username:"))
        self.username_entry = QLineEdit()
        self.username_entry.setPlaceholderText("Username")
        layout.addWidget(self.username_entry)
        layout.addWidget(QLabel("Password:"))
        self.password_entry = QLineEdit()
        self.password_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_entry.setPlaceholderText("Password")
        layout.addWidget(self.password_entry)
        page.setLayout(layout)
        return page

    def _create_device_code_page(self):
        page = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.device_code_info = QLabel(
            "Click Login to start device code authentication."
        )
        self.device_code_info.setWordWrap(True)
        layout.addWidget(self.device_code_info)

        code_layout = QHBoxLayout()
        self.device_code_label = QLabel("")
        self.device_code_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        code_layout.addWidget(self.device_code_label)
        self.open_browser_button = QPushButton("Open Browser")
        self.open_browser_button.setVisible(False)
        self.open_browser_button.clicked.connect(self._on_open_browser)
        code_layout.addWidget(self.open_browser_button)
        code_layout.addStretch()
        layout.addLayout(code_layout)

        self.device_code_status = QLabel("")
        layout.addWidget(self.device_code_status)

        page.setLayout(layout)
        return page

    def _on_login_clicked(self):
        method_index = self.auth_method_selector.currentIndex()
        if method_index == 1:  # API Key
            api_key = self.api_key_entry.text().strip()
            if api_key:
                self.api_key_submitted.emit(api_key)
        elif method_index == 2:  # Password
            username = self.username_entry.text().strip()
            password = self.password_entry.text().strip()
            if username and password:
                self.password_submitted.emit(username, password)
        elif method_index == 3:  # Device Code
            self.login_requested.emit()
        else:
            # No auth - just emit login request so connection proceeds
            self.login_requested.emit()

    def _on_logout_clicked(self):
        self.logout_requested.emit()

    def _on_open_browser(self):
        url = self._authorization_uri
        if url:
            webbrowser.open(url)

    # --- Methods called by the main widget to update UI state ---

    def set_auth_status(self, text, is_error=False):
        """Update the auth status label."""
        if is_error:
            self.status_label.setStyleSheet("color: red;")
        else:
            self.status_label.setStyleSheet("color: green;")
        self.status_label.setText(text)

    def set_logged_in(self, identity_info=""):
        """Update UI to reflect logged-in state."""
        self.login_button.setEnabled(False)
        self.logout_button.setEnabled(True)
        self.auth_method_selector.setEnabled(False)
        if identity_info:
            self.set_auth_status(f"Logged in as {identity_info}")
        else:
            self.set_auth_status("Authenticated")

    def set_logged_out(self):
        """Update UI to reflect logged-out state."""
        self.login_button.setEnabled(True)
        self.logout_button.setEnabled(False)
        self.auth_method_selector.setEnabled(True)
        self.status_label.setText("")
        self.status_label.setStyleSheet("")
        # Reset device code UI
        self.device_code_info.setText(
            "Click Login to start device code authentication."
        )
        self.device_code_label.setText("")
        self.device_code_status.setText("")
        self.open_browser_button.setVisible(False)

    def show_device_code(self, authorization_uri, user_code, expires_in):
        """Display device code flow information."""
        self._authorization_uri = authorization_uri
        minutes = int(expires_in) // 60
        self.device_code_info.setText(
            f"You have {minutes} minutes to visit the URL and enter the code:"
        )
        self.device_code_label.setText(user_code)
        self.open_browser_button.setVisible(True)
        self.device_code_status.setText("Waiting for authorization...")

    def show_device_code_polling(self):
        """Update status during device code polling."""
        self.device_code_status.setText("Waiting for authorization...")

    def set_auth_providers(self, providers):
        """Configure available auth methods based on server capabilities.

        Parameters
        ----------
        providers : list
            List of AboutAuthenticationProvider from the server.
        """
        self.auth_method_selector.blockSignals(True)
        self.auth_method_selector.clear()
        self.auth_method_selector.addItem("None")

        # Always allow API Key
        self.auth_method_selector.addItem("API Key")

        has_internal = False
        has_external = False
        for p in providers:
            mode = p.mode
            if mode in ("internal", "password"):
                has_internal = True
            elif mode == "external":
                has_external = True

        if has_internal:
            self.auth_method_selector.addItem("Password")
        if has_external:
            self.auth_method_selector.addItem("Device Code")

        # Auto-select if only one provider type
        if len(providers) == 1:
            mode = providers[0].mode
            if mode in ("internal", "password"):
                idx = self.auth_method_selector.findText("Password")
                self.auth_method_selector.setCurrentIndex(idx)
            elif mode == "external":
                idx = self.auth_method_selector.findText("Device Code")
                self.auth_method_selector.setCurrentIndex(idx)

        self.auth_method_selector.blockSignals(False)
        self.auth_stack.setCurrentIndex(
            self.auth_method_selector.currentIndex()
        )
