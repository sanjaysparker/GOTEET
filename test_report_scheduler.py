import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import engine
import report_scheduler as r

class SchedulerTests(unittest.TestCase):
    def test_ist_boundaries(self):
        at=dt.datetime.fromisoformat('2026-10-23T17:59:00+05:30')
        self.assertTrue(r.slots(at)['weekly'].startswith('2026-10-16T18:00'))
        self.assertTrue(r.slots(at+dt.timedelta(minutes=1))['weekly'].startswith('2026-10-23T18:00'))
        self.assertTrue(r.slots(at.replace(hour=8))['daily'].startswith('2026-10-22T09:00'))
    def test_disabled_does_not_collect(self):
        with patch.object(r.settings,'get',return_value={'auto_analysis':False}),patch.object(r.engine,'collect') as collect:
            r.tick();collect.assert_not_called()
    def test_persisted_dedup_and_next_day(self):
        import sqlite3
        import agent_observer
        with tempfile.TemporaryDirectory() as folder:
            def connect():
                c=sqlite3.connect(str(Path(folder)/'state.db'));c.row_factory=sqlite3.Row;return c
            prefs={'auto_analysis':True,'github_enabled':False,'local_index_enabled':False,'google_enabled':False}
            with patch.object(r.engine,'connect',side_effect=connect),patch.object(r.settings,'get',return_value=prefs),patch.object(r.engine,'report',return_value={'id':'report'}) as report,patch.object(r,'analyse_local') as analyse,patch.object(r.work,'notify'),patch.object(agent_observer,'safe_scan'):
                at=dt.datetime.fromisoformat('2026-10-23T18:01:00+05:30')
                r.tick(at);r.tick(at)
                self.assertEqual(report.call_count,2);self.assertEqual(analyse.call_count,1)
                r.tick(at+dt.timedelta(days=1))
                self.assertEqual(report.call_count,3);self.assertEqual(analyse.call_count,2)
if __name__=='__main__':unittest.main()
