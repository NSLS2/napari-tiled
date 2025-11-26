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
        print("In TiledSubscriber.init")
        print(self.client)
        self.sub = self.client.subscribe(QtExecutor())

    def run(self):
        self.sub.start()
        # this still gives 500 error


def on_new_child(update):
    "A new child node has been created in a container."
    child = update.child()
    print(child)
    ts = TiledSubscriber(child)
    # Is the child also a container?
    if child.structure_family == "container":
        # Recursively subscribe to the children of this new container.
        ts.sub.child_created.add_callback(on_new_child)
    else:
        # Subscribe to data updates (i.e. appended table rows or array slices).
        ts.sub.new_data.add_callback(on_new_data)
        # Launch the subscription.
        # Ask the server to replay from the very first update, if we already
        # missed some.
    ts.run()


def on_new_data(update):
    "Data has been updated (maybe appended) to an array or table."
    print(update.data())
