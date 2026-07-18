import os
import unittest

from server import cfparse

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "cf_problem.html")


class TestCfParse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, encoding="utf-8") as f:
            cls.parsed = cfparse.parse_problem(f.read())

    def test_title_strips_index(self):
        self.assertEqual(self.parsed["title"], "Watermelon Division")

    def test_limits(self):
        self.assertEqual(self.parsed["time_limit_ms"], 1000)
        self.assertEqual(self.parsed["memory_limit_mb"], 64)

    def test_statement_keeps_tex(self):
        self.assertIn("$$$w$$$", self.parsed["statement_html"])
        self.assertNotIn("problem-statement", self.parsed["statement_html"])

    def test_specs_drop_section_titles(self):
        self.assertIn("1 \\le w \\le 100", self.parsed["input_spec_html"])
        self.assertNotIn("section-title", self.parsed["input_spec_html"])
        self.assertIn("YES", self.parsed["output_spec_html"])

    def test_samples_including_line_divs(self):
        self.assertEqual(self.parsed["samples"],
                         [{"input": "8", "output": "YES"}, {"input": "5", "output": "NO"}])

    def test_tags_and_rating(self):
        self.assertEqual(self.parsed["tags"], ["math", "brute force"])
        self.assertEqual(self.parsed["rating"], 800)

    def test_note(self):
        self.assertIn("w = 8", self.parsed["note_html"].replace("$$$", ""))

    def test_url_parsing(self):
        self.assertEqual(cfparse.parse_problem_url("https://codeforces.com/problemset/problem/4/A"), (4, "A"))
        self.assertEqual(cfparse.parse_problem_url("https://codeforces.com/contest/1741/problem/F2"), (1741, "F2"))
        self.assertEqual(cfparse.parse_problem_url("https://codeforces.com/gym/104114/problem/B"), (104114, "B"))
        self.assertIsNone(cfparse.parse_problem_url("https://example.com/x"))

    def test_broken_page_raises(self):
        with self.assertRaises(cfparse.ParseError):
            cfparse.parse_problem("<html><body>maintenance</body></html>")


if __name__ == "__main__":
    unittest.main()
