from qtpy.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal


class QtExecutor:
    def __init__(self):
        self.threadpool = QThreadPool.globalInstance()

    def submit(self, f, *args):
        print("     In QtExecutor.submit")
        runnable = QRunnable.create(lambda: f(*args))
        self.threadpool.start(runnable)

    def shutdown(self, wait: bool = True):
        pass


class TiledSubscriberSignals(QObject):
    finished = Signal()
    results = Signal(object)


class TiledSubscriber(QThread):
    def __init__(
        self,
        client,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.signals = TiledSubscriberSignals()
        self.client = client

    def run(self):
        print("In TiledSubscriber.run")
        print(self.client)
        catalog_sub = self.client.subscribe(QtExecutor())
        catalog_sub.child_created.add_callback(on_new_child)
        print("About to start catalog_sub")
        catalog_sub.start()
        # this still gives 500 error


def on_new_child(update):
    "A new child node has been created in a container."
    child = update.child()
    print(child)
    sub = child.subscribe(QtExecutor())
    # Is the child also a container?
    if child.structure_family == "container":
        # Recursively subscribe to the children of this new container.
        sub.child_created.add_callback(on_new_child)
    else:
        # Subscribe to data updates (i.e. appended table rows or array slices).
        sub.new_data.add_callback(on_new_data)
        # Launch the subscription.
        # Ask the server to replay from the very first update, if we already
        # missed some.
    sub.start_in_thread(1)


def on_new_data(update):
    "Data has been updated (maybe appended) to an array or table."
    print(update.data())
