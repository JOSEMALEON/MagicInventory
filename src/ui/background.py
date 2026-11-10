from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal


class _TaskSignals(QObject):
    """
    QRunnable is not a QObject, so it can't emit signals by itself.
    This object carries the result back to the GUI thread.
    """

    succeeded = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):

    def __init__(self, function, signals):
        super().__init__()
        self.function = function
        self.signals = signals

    def run(self):
        # Runs in a worker thread: never touch widgets here
        try:
            result = self.function()
        except Exception as error:
            self._emit(self.signals.failed, error)
        else:
            self._emit(self.signals.succeeded, result)

    @staticmethod
    def _emit(signal, value):
        try:
            signal.emit(value)
        except RuntimeError:
            # The app was closed while this task was running: nobody is
            # waiting for the result anymore
            pass


class BackgroundRunner:
    """
    Run slow functions (network, disk) in a thread pool so the window
    never freezes. The callbacks always run in the GUI thread.
    """

    def __init__(self, max_threads=4):
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max_threads)

        # Keep the signal objects alive until their result has been delivered
        self._pending = set()

    def run(self, function, on_success=None, on_error=None):
        """
        Call function() in the background, then on_success(result) or
        on_error(exception) in the GUI thread.
        """

        signals = _TaskSignals()
        self._pending.add(signals)

        def handle_success(result):
            self._pending.discard(signals)
            if on_success:
                on_success(result)

        def handle_error(error):
            self._pending.discard(signals)
            if on_error:
                on_error(error)

        # Queued: the slot runs in the thread that owns `signals` (the GUI thread)
        signals.succeeded.connect(handle_success, Qt.ConnectionType.QueuedConnection)
        signals.failed.connect(handle_error, Qt.ConnectionType.QueuedConnection)

        self.pool.start(_Task(function, signals))
