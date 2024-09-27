"""
This module is an example of a barebones QWidget plugin for napari

It implements the Widget specification.
see: https://napari.org/plugins/guides.html?#widgets

Replace code below according to your needs.
"""

from qtpy.QtWidgets import QVBoxLayout, QWidget

from .models.search import ResultsPage
from .qt.search import SearchResults


class TiledBrowser2(QWidget):
    # your QWidget.__init__ can optionally request the napari viewer instance
    # in one of two ways:
    # 1. use a parameter called `napari_viewer`, as done here
    # 2. use a type annotation of 'napari.viewer.Viewer' for any parameter
    def __init__(self, napari_viewer):
        super().__init__()
        self.viewer = napari_viewer
        self.search = ResultsPage(uri=None)
        widget = SearchResults(self.search)
        layout = QVBoxLayout()
        layout.addWidget(widget)
        self.setLayout(layout)
