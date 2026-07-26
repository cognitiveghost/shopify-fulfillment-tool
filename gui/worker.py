import sys
import traceback

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    """Defines the signals available from a running worker thread.

    Supported signals:
        finished: Emitted when the task is done, regardless of outcome.
        error: Emitted when an exception occurs. Carries the exception info.
        result: Emitted when the task completes successfully. Carries the
                return value of the task function.
    """

    finished = Signal()
    error = Signal(tuple)
    result = Signal(object)


class Worker(QRunnable):
    """A generic, reusable worker thread that runs a function in the background.

    Inherits from QRunnable to be compatible with QThreadPool. This class is
    designed to take any function and its arguments, run it on a separate
    thread, and emit signals indicating the outcome (success, error, or
    completion).

    Attributes:
        fn (callable): The function to execute in the background.
        args (tuple): Positional arguments to pass to the function.
        kwargs (dict): Keyword arguments to pass to the function.
        signals (WorkerSignals): An object containing the signals that this
                                 worker can emit.
    """

    def __init__(self, fn, *args, **kwargs):
        """Initializes the Worker.

        Args:
            fn (callable): The function to execute in the background.
            *args: Positional arguments to pass to the function.
            **kwargs: Keyword arguments to pass to the function.
        """
        super().__init__()
        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        """Executes the target function in the background thread.

        This method is automatically called when the QRunnable is started by a
        QThreadPool. It wraps the function execution in a try...except block
        to catch any exceptions, emitting the `error` signal if one occurs,
        or the `result` signal on success. The `finished` signal is always
        emitted.
        """
        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done
