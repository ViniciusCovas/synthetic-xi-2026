"""Regression coverage for completed/legacy queues without API requests."""
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import unittest
import tempfile

from scripts.coverage_queue import QUEUE_COLUMNS, read_coverage_queue
from scripts import run_batched_selection_extraction as batched
from scripts import run_targeted_coverage_extraction as targeted


class CoverageQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_empty_queues(self):
        for contents in ['', '\n', ','.join(QUEUE_COLUMNS) + '\n']:
            with self.subTest(contents=contents):
                queue = self.root / 'queue.csv'
                queue.write_text(contents)
                self.assertTrue(read_coverage_queue(queue).empty)

    def test_populated_queue(self):
        queue = self.root / 'queue.csv'
        queue.write_text('player_id,fixture_id,window\n12,34,annual_current\n')
        self.assertEqual(read_coverage_queue(queue).iloc[0].fixture_id, 34)

    def test_invalid_queue(self):
        queue = self.root / 'queue.csv'
        queue.write_text('unexpected\nvalue\n')
        with self.assertRaisesRegex(ValueError, 'Invalid coverage queue'):
            read_coverage_queue(queue)

    def test_no_network_for_empty_queue(self):
        for module, client in [(batched, 'BatchClient'), (targeted, 'Client')]:
            with self.subTest(module=module.__name__):
                queue = self.root / 'queue.csv'
                queue.write_text('\n')
                status = self.root / 'audit' / 'status.json'
                with patch.object(module, 'PRIORITY_PATH', queue), patch.object(module, 'STATUS_PATH', status), patch.object(module, client) as network:
                    module.main()
                network.assert_not_called()
                self.assertEqual(json.loads(status.read_text()), {'status': 'no_missing_coverage_fixtures', 'network_calls': 0})

    def test_producer_schema(self):
        queue = pd.DataFrame([], columns=QUEUE_COLUMNS).drop_duplicates(
            ['player_id', 'fixture_id', 'window', 'priority_reason'])
        path = self.root / 'queue.csv'
        queue.to_csv(path, index=False)
        self.assertEqual(list(pd.read_csv(path).columns), QUEUE_COLUMNS)
