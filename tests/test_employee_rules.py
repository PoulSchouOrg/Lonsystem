import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

import pytest

from utils.employee_rules import (
    next_employee_number, validate_cpr, cpr_birthdate, mask_cpr, is_masked_cpr,
    one_month_before, in_alert_window, anniversary, round_birthday_alert, jubilee_alert,
)


# ── Lønnummer ──────────────────────────────────────────────────────────────

def test_next_number_is_highest_plus_one_without_filling_gaps():
    assert next_employee_number(["34637", "34640"]) == "34641"


def test_next_number_ignores_numbers_below_34000_and_non_numeric():
    assert next_employee_number(["33999", "1234", "TEST998", "34001"]) == "34002"


def test_next_number_continues_past_34999():
    assert next_employee_number(["34999"]) == "35000"


def test_next_number_defaults_to_34000():
    assert next_employee_number(["5", "TEST1"]) == "34000"
    assert next_employee_number([]) == "34000"


def test_next_number_ignores_blank_and_whitespace():
    assert next_employee_number(["", None, " 34100 "]) == "34101"


# ── CPR ────────────────────────────────────────────────────────────────────

def test_validate_cpr_accepts_valid():
    assert validate_cpr(" 120385-1234 ") == "120385-1234"


@pytest.mark.parametrize("bad", ["1203851234", "12038-51234", "120385-123", "abcdef-1234", "320185-1234", "120385-12345"])
def test_validate_cpr_rejects_wrong_format_or_date(bad):
    with pytest.raises(ValueError):
        validate_cpr(bad)


@pytest.mark.parametrize("cpr,expected", [
    ("120385-1234", date(1985, 3, 12)),   # 7. ciffer 1 → 1900
    ("120305-4234", date(2005, 3, 12)),   # 7. ciffer 4, år 05 → 2000
    ("120385-4234", date(1985, 3, 12)),   # 7. ciffer 4, år 85 → 1900
    ("120305-5234", date(2005, 3, 12)),   # 7. ciffer 5, år 05 → 2000
    ("120385-5234", date(1885, 3, 12)),   # 7. ciffer 5, år 85 → 1800
    ("120336-9234", date(2036, 3, 12)),   # 7. ciffer 9, år 36 → 2000
    ("120337-9234", date(1937, 3, 12)),   # 7. ciffer 9, år 37 → 1900
])
def test_cpr_birthdate_century_rule(cpr, expected):
    assert cpr_birthdate(cpr) == expected


def test_mask_cpr():
    assert mask_cpr("120385-1234") == "120385-****"
    assert mask_cpr(None) is None
    assert mask_cpr("") == ""


def test_is_masked_cpr():
    assert is_masked_cpr("120385-****") is True
    assert is_masked_cpr("120385-1234") is False
    assert is_masked_cpr(None) is False


# ── Advarselsvinduer ───────────────────────────────────────────────────────

def test_one_month_before_same_day_and_clamped():
    assert one_month_before(date(2026, 11, 15)) == date(2026, 10, 15)
    assert one_month_before(date(2026, 3, 31)) == date(2026, 2, 28)
    assert one_month_before(date(2026, 1, 10)) == date(2025, 12, 10)


def test_in_alert_window_inclusive_both_ends():
    event = date(2026, 11, 15)
    assert in_alert_window(event, date(2026, 10, 14)) is False
    assert in_alert_window(event, date(2026, 10, 15)) is True
    assert in_alert_window(event, date(2026, 11, 15)) is True
    assert in_alert_window(event, date(2026, 11, 16)) is False   # overskredet → ingen popup


def test_anniversary_handles_feb_29():
    assert anniversary(date(2000, 2, 29), 25) == date(2025, 2, 28)
    assert anniversary(date(2001, 6, 1), 25) == date(2026, 6, 1)


def test_round_birthday_alert_inside_window():
    # Fylder 40 den 15/11-2026 → vises fra 15/10-2026
    assert round_birthday_alert(date(1986, 11, 15), date(2026, 10, 20)) == (40, date(2026, 11, 15))


def test_round_birthday_alert_all_tens_including_10_and_20():
    assert round_birthday_alert(date(2016, 11, 15), date(2026, 11, 1)) == (10, date(2026, 11, 15))
    assert round_birthday_alert(date(2006, 11, 15), date(2026, 11, 1)) == (20, date(2026, 11, 15))


def test_round_birthday_alert_none_when_not_round_or_outside_window():
    assert round_birthday_alert(date(1987, 11, 15), date(2026, 11, 1)) is None   # 39 år
    assert round_birthday_alert(date(1986, 11, 15), date(2026, 10, 14)) is None  # for tidligt
    assert round_birthday_alert(date(1986, 11, 15), date(2026, 11, 16)) is None  # overskredet


def test_round_birthday_alert_across_new_year():
    # Fylder 50 den 5/1-2027, i dag 10/12-2026 → i vinduet (fra 5/12-2026)
    assert round_birthday_alert(date(1977, 1, 5), date(2026, 12, 10)) == (50, date(2027, 1, 5))


def test_jubilee_alert_25_40_50_only():
    assert jubilee_alert(date(2001, 11, 15), date(2026, 11, 1)) == (25, date(2026, 11, 15))
    assert jubilee_alert(date(1986, 11, 15), date(2026, 11, 1)) == (40, date(2026, 11, 15))
    assert jubilee_alert(date(1976, 11, 15), date(2026, 11, 1)) == (50, date(2026, 11, 15))
    assert jubilee_alert(date(1996, 11, 15), date(2026, 11, 1)) is None   # 30 år – ikke jubilæum
    assert jubilee_alert(date(2001, 11, 15), date(2026, 11, 16)) is None  # overskredet
