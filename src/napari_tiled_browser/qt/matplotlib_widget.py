from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import (
    NavigationToolbar2QT as NavigationToolbar,
)
from matplotlib.figure import Figure
from qtpy.QtWidgets import QVBoxLayout, QWidget


class MatplotlibWidget(QWidget):
    def __init__(self, parent=None, figsize=(5, 4)):
        super().__init__(parent=parent)
        self.figsize = figsize

        self.figure = Figure(figsize=self.figsize)
        self.canvas = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas)

        layout = QVBoxLayout()
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self.setLayout(layout)
