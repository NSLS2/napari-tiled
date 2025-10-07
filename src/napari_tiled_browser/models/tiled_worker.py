from qtpy.QtCore import QObject, QRunnable, Signal


class TiledWorkerSignals(QObject):
    finished = Signal()
    results = Signal(object)


class TiledWorker(QRunnable):
    def __init__(
        self,
        *,
        client,
        current_page,
        node_path_parts,
        rows_per_page,
        search_results,
        **kwargs,
    ):
        super().__init__()
        self.signals = TiledWorkerSignals()
        self.rows_per_page = rows_per_page
        self.current_page = current_page
        self.client = client
        self.search_results = search_results
        self.node_path_parts = node_path_parts

    def run(self):
        if self.search_results is None:
            catalog_or_search_results = self.client
        else:
            catalog_or_search_results = self.search_results

        node_offset = self.rows_per_page * self.current_page
        selection = slice(node_offset, node_offset + self.rows_per_page)

        if self.node_path_parts:
            results = catalog_or_search_results[
                self.node_path_parts[0]
            ].items()[selection]
        else:
            results = catalog_or_search_results.items()[selection]

        self.signals.finished.emit()
        self.signals.results.emit(results)
