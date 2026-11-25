import unittest
from .lounge import LoungeRoute


class TestLounge(unittest.TestCase):
    def setUp(self):
        self.route = LoungeRoute()

    def checkpoint(self, seen, marker):
        self.assertEqual(self.route.observe(seen)["status"], "expected_visible")
        self.assertTrue(self.route.confirm(marker))
        self.assertFalse(self.route.confirm(marker))

    def junction(self):
        self.checkpoint([10], 10)
        self.assertEqual(self.route.observe([30, 20])["status"], "choice_visible")
        self.assertFalse(self.route.confirm(None))

    def finish(self):
        self.checkpoint([50], 50)
        self.assertEqual(self.route.observe([60])["status"], "expected_visible")
        self.assertNotEqual(self.route.state, "complete")
        self.checkpoint([60], 60)
        self.assertEqual(self.route.observe([60])["status"], "complete")

    def test_direct_path(self):
        self.junction()
        self.assertTrue(self.route.choose("right")["text"])
        self.assertIsNone(self.route.choose("left"))
        self.finish()

    def test_recovery_single_or_paired_sign(self):
        for seen in ([30], [30, 20]):
            self.route.reset()
            self.junction()
            self.assertTrue(self.route.choose("left")["text"])
            self.assertEqual(self.route.observe([50])["status"], "out_of_order")
            self.assertIn("Turn around", self.route.observe([40])["text"])
            self.checkpoint([40], 40)
            self.assertIsNone(self.route.observe([50])["text"])
            self.checkpoint(seen, 30)
            self.finish()

    def test_no_selection_from_partial_lost_or_ambiguous_pair(self):
        self.junction()
        for seen in ([30], [20], [], [20,30,50], [99]):
            self.route.observe([20,30])
            self.assertIsNone(self.route.observe(seen)["text"])
            self.assertIsNone(self.route.choose("left"))
            self.assertFalse(self.route.confirm(30))

    def test_no_stale_confirmation_or_shortcut(self):
        self.route.observe([10])
        self.route.observe([])
        self.assertFalse(self.route.confirm(10))
        self.assertIsNone(self.route.observe([60])["text"])
        self.junction()
        self.route.reset()
        self.assertIsNone(self.route.choose("right"))
        self.assertEqual(self.route.observe([10])["status"], "expected_visible")
