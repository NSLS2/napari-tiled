from qtpy.QtCore import QObject, QRunnable, Signal


class TiledSubscriberSignals(QObject):
    finished = Signal()
    results = Signal(object)


class TiledSubscriber(QRunnable):
    def __init__(
        self,
        *,
        client,
        node_path_parts,
        **kwargs,
    ):
        super().__init__()
        self.signals = TiledSubscriberSignals()
        self.client = client
        self.node_path_parts = node_path_parts

    def run(self):
        catalog_sub = self.client.subscribe()
        catalog_sub.child_created.add_callback(on_new_child)
        catalog_sub.start()


def on_new_child(update):
    "A new child node has been created in a container."
    child = update.child()
    print(child)
    sub = child.subscribe()
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
