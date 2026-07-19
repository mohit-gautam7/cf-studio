"""best_test_array must survive models that echo the schema or emit placeholders."""
import unittest

from server.ai import best_test_array


class TestBestTestArray(unittest.TestCase):
    def test_ignores_echoed_format_example(self):
        reply = ('I will reply in the format [{"input": "...", "expected": "...", "reason": "..."}].\n'
                 'Here are the tests:\n'
                 '[{"input": "1", "expected": "NO", "reason": "min"},'
                 ' {"input": "8", "expected": "YES", "reason": "even"}]')
        tests = best_test_array(reply)
        self.assertEqual(len(tests), 2)
        self.assertEqual(tests[0]["input"], "1\n")
        self.assertEqual(tests[1]["expected"], "YES")

    def test_drops_placeholder_entries_keeps_real(self):
        reply = '[{"input": "...", "expected": "..."}, {"input": "5 9\\n2 7 11 15 1", "expected": "YES", "reason": "pair"}]'
        tests = best_test_array(reply)
        self.assertEqual(len(tests), 1)
        self.assertIn("2 7 11 15 1", tests[0]["input"])

    def test_fenced_json(self):
        reply = 'Sure!\n```json\n[{"input": "3\\n1 7 3", "expected": "4", "reason": "sample"}]\n```'
        tests = best_test_array(reply)
        self.assertEqual(len(tests), 1)
        self.assertEqual(tests[0]["expected"], "4")

    def test_all_placeholders_gives_empty(self):
        self.assertEqual(best_test_array('[{"input": "...", "expected": "..."}]'), [])
        self.assertEqual(best_test_array("no json at all"), [])

    def test_picks_largest_valid_array(self):
        reply = ('[{"input": "1", "expected": "a"}] and the full set: '
                 '[{"input": "1", "expected": "a"}, {"input": "2", "expected": "b"}, {"input": "3", "expected": "c"}]')
        self.assertEqual(len(best_test_array(reply)), 3)


if __name__ == "__main__":
    unittest.main()
