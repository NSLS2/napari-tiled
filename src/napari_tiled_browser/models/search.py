from napari.utils.events import EmitterGroup, Event
from tiled.client import from_uri

DEFAULT_PAGE_LIMIT = 20


class ResultsPage:
    def __init__(self, *, uri=None):
        self._uri = None
        self._client = None
        self._total_length = 0
        self._page_number = 0
        self._page_limit = DEFAULT_PAGE_LIMIT
        self.queries = []
        self.results = []
        self.events = EmitterGroup(
            source=self,
            auto_connect=True,
            page_number=Event,
            page_limit=Event,
            refreshed=Event,
            connected=Event,
            uri=Event,
        )
        self.events.page_number.connect(self.refresh)
        self.events.page_limit.connect(self.refresh)
        self.events.connected.connect(self.refresh)
        self.uri = uri

    @property
    def page_number(self):
        return self._page_number

    @page_number.setter
    def page_number(self, value):
        self._page_number = value
        self.events.page_number(value=value)

    @property
    def page_limit(self):
        return self._page_limit

    @page_limit.setter
    def page_limit(self, value):
        self._page_limit = value
        self.events.page_limit(value=value)

    @property
    def range(self):
        return (
            self.page_number * self.page_limit,
            min((1 + self.page_number) * self.page_limit, self._total_length),
        )

    @property
    def total_length(self):
        return self._total_length

    @property
    def uri(self):
        return self._uri

    @uri.setter
    def uri(self, value):
        if value == self._uri:
            return
        self._uri = value
        self.events.uri(value=value)
        if value == "":
            self._client = None
        else:
            self._client = from_uri(value)
            self.events.connected()

    def refresh(self, event):
        if self._client is None:
            return []
        results = self._client
        for query in self.queries:
            results = results.search(query)
        self._total_length = len(results)
        self.results.clear()
        self.results.extend(
            results.keys()[
                (self.page_number * self.page_limit) : (  # noqa E203
                    (1 + self.page_number) * self.page_limit
                )
            ]
        )
        self.events.refreshed()
