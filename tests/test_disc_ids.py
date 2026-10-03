import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import gui

class DiscIdentityTests(unittest.TestCase):
    def test_modded_ids_and_revisions(self):
        for key, (_, _, delta, identity, version) in gui.dist.TARGETS.items():
            self.assertEqual(gui.key_for(identity, version)[0], key)
            self.assertEqual(gui.key_for(identity[:4] + '99', version)[2], delta)
        self.assertEqual(gui.key_for('ZZZZ99', 0), (None, None, None))
        self.assertEqual(gui.key_for('RUUE99', 255), (None, None, None))
        self.assertEqual(gui.match_disc_id('RUUK99', gui.KOREA), 'RUUK01')
        self.assertEqual(gui.match_disc_id('RUUK02', gui.KOREA), 'RUUK02')
