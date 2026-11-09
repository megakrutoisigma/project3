import unittest

import metrics_history as metrics


class HistoryTests(unittest.TestCase):
    def setUp(self):
        metrics.clear_history()

    def tearDown(self):
        metrics.clear_history()

    def test_history_is_bounded_and_ordered(self):
        for value in range(130):
            metrics.save(dict(cpu=value, ram=20, disk=30, net_sent=0,
                              net_recv=0, processes=10))
        samples = metrics.history()
        self.assertEqual(len(samples), 120)
        self.assertEqual(samples[0]['cpu'], 10)
        self.assertEqual(samples[-1]['cpu'], 129)
        samples[-1]['cpu'] = -1
        self.assertEqual(metrics.history(1)[0]['cpu'], 129)
        metrics.clear_history()
        self.assertEqual(metrics.history(), [])
