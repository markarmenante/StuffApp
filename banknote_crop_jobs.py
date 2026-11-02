"""Bound optional crop computation without accumulating abandoned workers.

The callable must only compute a result; its caller owns publishing that result.
A timeout stops waiting, not the computation, so its slot remains occupied until
the daemon worker actually exits. Results arriving after a timeout are discarded.
"""
import math
import threading
import time


class CropBusy(RuntimeError):
    """All crop workers are still computing earlier requests."""


class CropTimeout(TimeoutError):
    """The optional crop did not finish within the caller's time budget."""


class CropRunner:
    def __init__(self, max_workers=2, default_timeout=45.0):
        if not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError('max_workers must be a positive integer')
        self.default_timeout = self._timeout(default_timeout)
        self._slots = threading.BoundedSemaphore(max_workers)

    @staticmethod
    def _timeout(value):
        timeout = float(value)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be a finite positive number')
        return timeout

    def run(self, compute, timeout=None):
        timeout = self._timeout(self.default_timeout if timeout is None else timeout)
        deadline = time.monotonic() + timeout
        if not self._slots.acquire(blocking=False):
            raise CropBusy('Optional crop workers are busy; original photos were retained.')

        finished = threading.Event()
        outcome = []

        def work():
            try:
                outcome.append((True, compute()))
            except BaseException as error:
                outcome.append((False, error))
            finally:
                # Releasing here, rather than in the waiting caller, keeps the
                # limit effective even when computation outlives its deadline.
                self._slots.release()
                finished.set()

        try:
            worker = threading.Thread(target=work, name='banknote-optional-crop', daemon=True)
            worker.start()
        except BaseException:
            self._slots.release()
            raise

        if not finished.wait(max(0.0, deadline - time.monotonic())):
            raise CropTimeout('Optional crop timed out; original photos were retained.')
        succeeded, value = outcome[0]
        if not succeeded:
            raise value
        return value


_runner = CropRunner()


def run(compute, timeout=None):
    """Return a computed crop, or raise promptly when busy or over budget."""
    return _runner.run(compute, timeout=timeout)
