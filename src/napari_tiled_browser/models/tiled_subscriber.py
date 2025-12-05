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

        self.mapping = {
            "stream_closed": self.stream_closed,
            "disconnected": self.disconnected,
        }

        self.sub.stream_closed.add_callback(self._emit)
        self.sub.disconnected.add_callback(self._emit)

    def _emit(self, update):
        self.mapping[update.type].emit(update)


class QtArraySubscription(QtTiledSubscription):
    new_data = Signal(object)  # emits LiveArrayData/LiveArrayRef

    def __init__(self, subscription: ArraySubscription):
        super().__init__(subscription)
        self.mapping.update(
            {
                "array-data": self.new_data,
                "array-ref": self.new_data,
            }
        )
        self.sub.new_data.add_callback(self._emit)


class QtContainerSubscription(QtTiledSubscription):
    child_created = Signal(object)
    child_metadata_updated = Signal(object)

    def __init__(self, subscription: ContainerSubscription):
        super().__init__(subscription)

        self.mapping.update(
            {
                "container-child-created": self.child_created,
                "container-child-metadata-updated": self.child_metadata_updated,
            }
        )

        self.sub.child_created.add_callback(self._emit)
        self.sub.child_metadata_updated.add_callback(self._emit)


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
    plottable_array_data_received = Signal(
        object, str  # data to plot; child_node_path, name of image
    )

    def __init__(self):
        super().__init__()
        self.active_subs = []
        self.create_subscription.connect(self.on_create_subscription)

    def on_create_subscription(self, child):
        sub = child.subscribe(executor=QtExecutor())
        # Is the child also a container?
        if child.structure_family == "container":
            # Recursively subscribe to the children of this new container.
            ts = QtContainerSubscription(sub)
            ts.child_created.connect(self.on_new_child)
        elif child.structure_family == "array":
            # Subscribe to data updates (i.e. appended table rows or array slices).
            ts = QtArraySubscription(sub)
            ts.new_data.connect(self.on_new_data)
            # Launch the subscription.
            # Ask the server to replay from the very first update, if we already
            # missed some.
        else:
            # Ignore other structures (e.g. tables) for now.
            ts = None
        if ts is None:
            return
        thread = TiledSubscriptionThread(ts)
        thread.start(1)
        self.active_subs.append(thread)

    def on_new_child(self, update):
        "A new child node has been created in a container."
        child = update.child()

        self.create_subscription.emit(child)

    def on_new_data(self, update):
        "Data has been updated (maybe appended) to an array or table."
        self.plottable_array_data_received.emit(
            update.data(), "/".join(update.subscription.segments)
        )

    def clear(self):
        # TODO: Fix AttributeError
        # 'ContainerSubscription' object has no attribute 'type'
        for thread in self.active_subs:
            thread.ts.sub.disconnect()
        self.active_subs.clear()
