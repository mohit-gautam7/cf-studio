"""Original demo problems (CF-style) so the app works before any import."""
import json

from . import db

PROBLEMS = [
    {
        "title": "Even Split",
        "rating": 800, "tags": ["math"], "time_limit_ms": 1000,
        "statement_html": "<p>Aman bought a bag of $$$n$$$ identical candies and wants to split it between his two younger brothers so that both get exactly the same number of candies. Candies cannot be cut.</p><p>Determine whether such a split is possible.</p>",
        "input_spec_html": "<p>The only line contains one integer $$$n$$$ ($$$1 \\le n \\le 10^{18}$$$) — the number of candies.</p>",
        "output_spec_html": "<p>Print <code>YES</code> if the candies can be split equally, otherwise print <code>NO</code>.</p>",
        "note_html": "<p>Watch the limits: $$$n$$$ does not fit in a 32-bit integer.</p>",
        "samples": [{"input": "4", "output": "YES"}, {"input": "7", "output": "NO"}],
        "reference_solution": "n = int(input())\nprint('YES' if n % 2 == 0 else 'NO')\n",
    },
    {
        "title": "Largest Gap",
        "rating": 1000, "tags": ["implementation", "sortings"], "time_limit_ms": 2000,
        "statement_html": "<p>You are given an array $$$a$$$ of $$$n$$$ integers. Sort it in non-decreasing order and find the largest difference between two neighbouring elements.</p>",
        "input_spec_html": "<p>The first line contains one integer $$$n$$$ ($$$2 \\le n \\le 2 \\cdot 10^5$$$). The second line contains $$$n$$$ integers $$$a_1, a_2, \\ldots, a_n$$$ ($$$-10^9 \\le a_i \\le 10^9$$$).</p>",
        "output_spec_html": "<p>Print one integer — the maximum of $$$a_{i+1} - a_i$$$ over the sorted array.</p>",
        "note_html": "<p>In the first sample the sorted array is $$$[1, 3, 7]$$$; the gaps are $$$2$$$ and $$$4$$$.</p>",
        "samples": [{"input": "3\n1 7 3", "output": "4"}, {"input": "2\n5 5", "output": "0"}],
        "reference_solution": "n = int(input())\na = sorted(map(int, input().split()))\nprint(max(a[i+1] - a[i] for i in range(n - 1)))\n",
    },
    {
        "title": "Two Sum Exists",
        "rating": 1200, "tags": ["binary search", "two pointers", "sortings"], "time_limit_ms": 2000,
        "statement_html": "<p>You are given an array $$$a$$$ of $$$n$$$ integers and a target value $$$x$$$. Decide whether there exist two different positions $$$i \\ne j$$$ such that $$$a_i + a_j = x$$$.</p>",
        "input_spec_html": "<p>The first line contains two integers $$$n$$$ and $$$x$$$ ($$$2 \\le n \\le 2 \\cdot 10^5$$$, $$$1 \\le x \\le 2 \\cdot 10^9$$$). The second line contains $$$n$$$ integers $$$a_1, \\ldots, a_n$$$ ($$$1 \\le a_i \\le 10^9$$$).</p>",
        "output_spec_html": "<p>Print <code>YES</code> if such a pair exists, otherwise <code>NO</code>.</p>",
        "note_html": "<p>An $$$O(n^2)$$$ scan is too slow at $$$n = 2 \\cdot 10^5$$$: sort and use two pointers, or use a hash set.</p>",
        "samples": [{"input": "5 9\n2 7 11 15 1", "output": "YES"}, {"input": "3 10\n1 2 3", "output": "NO"}],
        "reference_solution": "import sys\ndata = sys.stdin.read().split()\nn, x = int(data[0]), int(data[1])\na = sorted(map(int, data[2:2 + n]))\ni, j = 0, n - 1\nok = False\nwhile i < j:\n    s = a[i] + a[j]\n    if s == x:\n        ok = True\n        break\n    if s < x:\n        i += 1\n    else:\n        j -= 1\nprint('YES' if ok else 'NO')\n",
    },
    {
        "title": "Staircase Ways",
        "rating": 1100, "tags": ["dp", "math"], "time_limit_ms": 2000,
        "statement_html": "<p>A staircase has $$$n$$$ steps. From any position you may climb either $$$1$$$ or $$$2$$$ steps. Count the number of distinct ways to reach the top, modulo $$$10^9 + 7$$$.</p>",
        "input_spec_html": "<p>The only line contains one integer $$$n$$$ ($$$1 \\le n \\le 10^6$$$).</p>",
        "output_spec_html": "<p>Print one integer — the number of ways modulo $$$10^9 + 7$$$.</p>",
        "note_html": "<p>For $$$n = 3$$$ the ways are $$$1{+}1{+}1$$$, $$$1{+}2$$$, $$$2{+}1$$$.</p>",
        "samples": [{"input": "3", "output": "3"}, {"input": "5", "output": "8"}],
        "reference_solution": "n = int(input())\nMOD = 10**9 + 7\na, b = 1, 1  # ways(0), ways(1)\nfor _ in range(n - 1):\n    a, b = b, (a + b) % MOD\nprint(b % MOD)\n",
    },
]


def seed_if_empty():
    with db.connect() as con:
        count = con.execute("SELECT COUNT(*) c FROM problems").fetchone()["c"]
        if count:
            return 0
        for p in PROBLEMS:
            con.execute(
                """INSERT INTO problems (source, title, rating, tags, time_limit_ms, memory_limit_mb,
                   statement_html, input_spec_html, output_spec_html, note_html, samples,
                   reference_solution, reference_language, created_at)
                   VALUES ('local',?,?,?,?,256,?,?,?,?,?,?, 'python', ?)""",
                (p["title"], p["rating"], json.dumps(p["tags"]), p["time_limit_ms"],
                 p["statement_html"], p["input_spec_html"], p["output_spec_html"], p["note_html"],
                 json.dumps(p["samples"]), p["reference_solution"], db.now()))
        return len(PROBLEMS)
