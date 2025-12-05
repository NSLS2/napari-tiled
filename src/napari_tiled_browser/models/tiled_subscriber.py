from qtpy.QtCore import QObject, QRunnable, QThread, QThreadPool, Signal
from tiled.client.stream import (
    ArraySubscription,
    ContainerSubscription,
    Subscription,
)


class QtExecutor:
    "Wrap QThreadPool in a concurrent.futures.Executor API"

    def __init__(self):
        self.threadpool = QThreadPool.globalInstance()

    def submit(self, f, *args):
        print("     In QtExecutor.submit")
        runnable = QRunnable.create(lambda: f(*args))
        self.threadpool.start(runnable)

    def shutdown(self, wait: bool = True):
        # Nothing to do. We must not shut down the global QThreadPool.
        # Qt takes care of this at application shutdown.
        pass


class QtTiledSubscription(QObject):
    stream_closed = Signal(object)
    disconnected = Signal(object)

    def __init__(self, subscription: Subscription):
        super().__init__()
        self.sub = subscription

        print(f"QtTiledSub... {self.sub}")
        self.sub.stream_closed.add_callback(self.stream_closed.emit)
        self.sub.disconnected.add_callback(self.disconnected.emit)


class QtArraySubscription(QtTiledSubscription):
    new_data = Signal(object)  # emits LiveArrayData/LiveArrayRef

    def __init__(self, subscription: ArraySubscription):
        super().__init__(subscription)
        self.sub.new_data.add_callback(self.new_data.emit)


class QtContainerSubscription(QtTiledSubscription):
    child_created = Signal(object)
    child_metadata_updated = Signal(object)

    def __init__(self, subscription: ContainerSubscription):
        super().__init__(subscription)
        print(f"!!!! {self.sub}")

    def add_callbacks(self):
        self.sub.child_created.add_callback(self.child_created.emit)
        self.sub.child_metadata_updated.add_callback(
            self.child_metadata_updated.emit
        )


class TiledSubscriptionThread(QThread):
    "Longrunning thread that follows the lifecycle of the websocket"

    def __init__(
        self,
        ts: QtTiledSubscription,
    ):
        super().__init__()
        self.ts = ts

    def run(self):
        # this blocks until self.sub.disconnect()
        self.ts.sub.start(1)


class SubscriptionManager(QObject):
    create_subscription = Signal(object)

    def __init__(self):
        super().__init__()
        self.active_subs = []
        self.create_subscription.connect(self.on_create_subscription)

    def on_create_subscription(self, child):
        # self.on_new_child(child)
        sub = child.subscribe(executor=QtExecutor())
        print(f"Have sub: {sub}")
        # Is the child also a container?
        if child.structure_family == "container":
            print("     container")
            # Recursively subscribe to the children of this new container.
            ts = QtContainerSubscription(sub)
            # print(ts)
            ts.child_created.connect(self.on_new_child)
            # ts.child_created.emit(sub)
            ts.add_callbacks()
        elif child.structure_family == "array":
            print("         array")
            # Subscribe to data updates (i.e. appended table rows or array slices).
            ts = QtArraySubscription(sub)
            ts.new_data.connect(self.on_new_data)
            # Launch the subscription.
            # Ask the server to replay from the very first update, if we already
            # missed some.
        else:
            # Ignore other structures (e.g. tables) for now.
            pass
        thread = TiledSubscriptionThread(ts)
        thread.start(1)
        self.active_subs.append(thread)

    def on_new_child(self, update):
        "A new child node has been created in a container."
        print("new child HERE!!!")
        child = update.child()
        print(child)

        self.create_subscription.emit(child)

    def on_new_data(self, update):
        "Data has been updated (maybe appended) to an array or table."
        print("new data HERE!!!")
        print(update.data())

    def clear(self):
        print(self.active_subs)
        for thread in self.active_subs:
            thread.ts.sub.disconnect()
        self.active_subs.clear()
