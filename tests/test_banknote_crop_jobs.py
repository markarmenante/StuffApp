"""Optional crop deadlines must not create unbounded background work."""
import threading
import time
import unittest
from unittest.mock import patch

import banknote_crop_jobs as jobs


class CropRunnerTests(unittest.TestCase):
    def test_timeout_returns_while_daemon_computation_is_still_running(self):
        runner = jobs.CropRunner(max_workers=1, default_timeout=0.05)
        release = threading.Event()
        started = threading.Event()
        workers = []

        def compute():
            workers.append(threading.current_thread())
            started.set()
            release.wait(5)
            return 'too late'

        try:
            before = time.monotonic()
            with self.assertRaises(jobs.CropTimeout):
                runner.run(compute)
            self.assertLess(time.monotonic() - before, 1.5)
            self.assertTrue(started.wait(1))
            self.assertTrue(workers[0].daemon)
            self.assertTrue(workers[0].is_alive())
            with self.assertRaises(jobs.CropBusy):
                runner.run(lambda: 'must not run')
        finally:
            release.set()
            for worker in workers:
                worker.join(2)
        # A late result has no path back to a subsequent caller.
        self.assertEqual(runner.run(lambda: 'fresh', timeout=1), 'fresh')

    def test_two_timed_out_computations_retain_both_slots_without_queueing(self):
        runner = jobs.CropRunner(default_timeout=0.05)
        releases = [threading.Event(), threading.Event()]
        started = [threading.Event(), threading.Event()]
        workers = []

        def blocked(index):
            workers.append(threading.current_thread())
            started[index].set()
            releases[index].wait(5)

        try:
            for index in range(2):
                with self.assertRaises(jobs.CropTimeout):
                    runner.run(lambda index=index: blocked(index))
                self.assertTrue(started[index].wait(1))
            with patch.object(jobs.threading, 'Thread') as new_thread:
                for _ in range(3):
                    with self.assertRaises(jobs.CropBusy):
                        runner.run(lambda: self.fail('Busy crop must not execute'))
                new_thread.assert_not_called()

            releases[0].set()
            workers[0].join(2)
            self.assertFalse(workers[0].is_alive())
            self.assertTrue(workers[1].is_alive())
            self.assertEqual(runner.run(lambda: 'available', timeout=1), 'available')
        finally:
            for release in releases:
                release.set()
            for worker in workers:
                worker.join(2)

    def test_success_and_error_release_capacity(self):
        runner = jobs.CropRunner(max_workers=1)
        expected = {'data': b'crop'}
        self.assertIs(runner.run(lambda: expected), expected)
        failure = ValueError('Crop rejected')

        def fail():
            raise failure

        with self.assertRaises(ValueError) as caught:
            runner.run(fail)
        self.assertIs(caught.exception, failure)
        self.assertIsNone(runner.run(lambda: None))

    def test_thread_start_failure_releases_capacity(self):
        runner = jobs.CropRunner(max_workers=1)
        with patch.object(jobs.threading.Thread, 'start', side_effect=RuntimeError('Cannot start')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot start'):
                runner.run(lambda: None)
        self.assertEqual(runner.run(lambda: 'available'), 'available')

    def test_invalid_timeout_does_not_start_work(self):
        runner = jobs.CropRunner()
        with patch.object(jobs.threading, 'Thread') as new_thread:
            for timeout in (0, -1, float('inf'), float('nan')):
                with self.assertRaises(ValueError):
                    runner.run(lambda: None, timeout=timeout)
            new_thread.assert_not_called()


if __name__ == '__main__':
    unittest.main()
