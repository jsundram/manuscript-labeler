"""tools/score_staves.py's matching: a kept staff is found, a line off,
or missed; a detected staff no kept one explains is extra."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from score_staves import score  # noqa: E402

SPACE = 0.01  # page fractions: a staff 0.04 tall


def staff(top):
    return {"top": top, "bottom": top + 4 * SPACE}


def test_a_staff_within_half_a_space_is_found():
    r = score([staff(0.1)], [staff(0.1 + 0.4 * SPACE)])
    assert (r["found"], r["line_off"], r["missed"], r["extra"]) == (1, 0, 0, 0)


def test_a_staff_one_space_away_is_a_line_off_not_extra():
    r = score([staff(0.1)], [staff(0.1 + SPACE)])
    assert (r["found"], r["line_off"], r["missed"], r["extra"]) == (0, 1, 0, 0)


def test_a_staff_stretched_a_space_is_neither():
    # top on the staff, bottom a line low: not the same staff a line off
    r = score([staff(0.1)], [{"top": 0.1, "bottom": 0.1 + 5 * SPACE}])
    assert (r["found"], r["line_off"], r["missed"], r["extra"]) == (0, 0, 1, 1)


def test_no_staff_near_is_missed_and_a_stray_one_extra():
    r = score([staff(0.1)], [staff(0.5)])
    assert (r["found"], r["line_off"], r["missed"], r["extra"]) == (0, 0, 1, 1)
