import unittest
from .direction_checkpoint import locate_objects, Route

class TestModule(unittest.TestCase):
    def test_positions_and_boundaries(self):
        for x, side in [(30,"left"),(100,"centre"),(190,"centre"),(200,"right")]:
            self.assertEqual(locate_objects(300,100,[dict(label="chair",bbox=[x-5,0,x+5,50])])[0]["position"],side)

    def test_invalid_and_empty_boxes(self):
        self.assertEqual(locate_objects(640,480,[]),[])
        with self.assertRaises(ValueError):
            locate_objects(640,480,[dict(label="chair",bbox=[800,0,820,40])])

    def test_no_accidental_progress(self):
        r=Route()
        for ids, status in [([20],"out_of_order"),([49],"unknown"),([10,20],"ambiguous"),([],"not_visible")]:
            self.assertEqual(r.observe(ids)["status"],status)
            self.assertFalse(r.confirm(10))
        r.observe([10]); r.observe([])
        self.assertFalse(r.confirm(10))

    def test_route(self):
        r=Route()
        for i in (10,20,30):
            event=r.observe([i])
            self.assertTrue(event["text"])
            self.assertEqual(event,r.observe([i]))
            self.assertTrue(r.confirm(i))
            self.assertFalse(r.confirm(i))
        self.assertEqual(r.observe([30])["status"],"complete")
        r.reset()
        self.assertEqual(r.observe([10])["status"],"expected_visible")
