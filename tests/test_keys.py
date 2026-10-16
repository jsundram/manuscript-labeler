"""Key signatures one part writes and the others don't (static/app.js
keyDisagreements, run under node; skipped without node)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def disagreements(rows):
    src = (ROOT / "static" / "app.js").read_text()
    js = "\n".join([
        re.search(r"function keyDisagreements\(rows\) \{.*?\n\}", src, re.S).group(0),
        f"const rows = {json.dumps(rows)}.map(([part, movement, bar, count, key]) => ({{ nb: {{ part, movement, bar, count }}, key }}));",
        "console.log(JSON.stringify(keyDisagreements(rows).map(d => [d.part, d.key, d.others, d.first.bar, d.last.bar])));",
    ])
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def part(name, keys, movement="II", start=1):
    return [[name, movement, start + i, 1, k] for i, k in enumerate(keys)]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_a_slip_in_one_part_is_a_run_of_bars():
    flats = [-2] * 6
    rows = part("vn1", flats) + part("vn2", flats) + part("va", flats) + part("vc", [-2, 1, 1, 1, -2, -2])
    assert disagreements(rows) == [["vc", 1, -2, 2, 4]]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_a_change_all_parts_make_or_a_part_alone_is_no_disagreement():
    change = [1, 1, -2, -2]
    rows = part("vn1", change) + part("vn2", change) + part("va", change) + part("vc", change)
    assert disagreements(rows) == []
    # two parts against two: no majority to go by; one other part: too few
    assert disagreements(part("vn1", [1, 1]) + part("vn2", [1, 1]) + part("va", [2, 2]) + part("vc", [2, 2])) == []
    assert disagreements(part("vn1", [1, 1]) + part("vc", [2, 2])) == []
