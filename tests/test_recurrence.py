import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date
from calculators.recurrence import occurrence_dates, describe, one_year_after, MAX_OCCURRENCES


def _weekly(weekdays, start, **kw):
    args = dict(end_mode="count", end_count=None, end_date=None, holidays=set(), skip_holidays=True)
    args.update(kw)
    return occurrence_dates("weekly", weekdays, start, **args)


def test_weekly_single_day_count():
    # Tirsdag 13-10-2026, hver tirsdag, 3 gange
    assert _weekly([1], date(2026, 10, 13), end_count=3) == [
        date(2026, 10, 13), date(2026, 10, 20), date(2026, 10, 27)]


def test_weekly_multiple_days_count_counts_days():
    # Mandag 12-10-2026, hver mandag og torsdag, 4 gange → man, tors, man, tors
    assert _weekly([0, 3], date(2026, 10, 12), end_count=4) == [
        date(2026, 10, 12), date(2026, 10, 15), date(2026, 10, 19), date(2026, 10, 22)]


def test_start_date_not_in_pattern_is_not_an_occurrence():
    # Startdato onsdag, mønster kun mandag
    assert _weekly([0], date(2026, 10, 14), end_count=2) == [date(2026, 10, 19), date(2026, 10, 26)]


def test_weekly_end_date_inclusive():
    assert _weekly([1], date(2026, 10, 13), end_mode="date", end_date=date(2026, 10, 27)) == [
        date(2026, 10, 13), date(2026, 10, 20), date(2026, 10, 27)]


def test_holiday_skipped_and_replaced_when_counting():
    hol = {date(2026, 10, 20)}
    assert _weekly([1], date(2026, 10, 13), end_count=3, holidays=hol) == [
        date(2026, 10, 13), date(2026, 10, 27), date(2026, 11, 3)]


def test_holiday_not_skipped_for_comment_only():
    hol = {date(2026, 10, 20)}
    assert _weekly([1], date(2026, 10, 13), end_count=2, holidays=hol, skip_holidays=False) == [
        date(2026, 10, 13), date(2026, 10, 20)]


def test_monthly_nth_weekday():
    # 13-10-2026 er 2. tirsdag i oktober
    got = occurrence_dates("monthly", [], date(2026, 10, 13), "count", 3, None, set(), True)
    assert got == [date(2026, 10, 13), date(2026, 11, 10), date(2026, 12, 8)]


def test_monthly_fifth_weekday_means_last():
    # 29-10-2026 er 5. torsdag i oktober → sidste torsdag hver måned
    got = occurrence_dates("monthly", [], date(2026, 10, 29), "count", 3, None, set(), True)
    assert got == [date(2026, 10, 29), date(2026, 11, 26), date(2026, 12, 31)]


def test_limit_one_year():
    got = _weekly([0], date(2026, 10, 12), end_mode="date", end_date=date(2028, 1, 1))
    assert got[-1] <= one_year_after(date(2026, 10, 12))
    assert got[-1] == date(2027, 10, 11)


def test_limit_100_occurrences():
    got = _weekly([0, 1, 2, 3, 4], date(2026, 10, 12), end_count=500)
    assert len(got) == MAX_OCCURRENCES


def test_after_and_existing_count_extend_from_end():
    # Serie med 3 eksisterende (sidste 27-10), forlæng til 5 i alt
    got = _weekly([1], date(2026, 10, 13), end_count=5, after=date(2026, 10, 27), existing_count=3)
    assert got == [date(2026, 11, 3), date(2026, 11, 10)]


def test_existing_count_respects_global_max():
    got = _weekly([1], date(2026, 10, 13), end_mode="date", end_date=date(2027, 10, 1),
                  after=date(2026, 10, 13), existing_count=99)
    assert len(got) == 1


def test_one_year_after_leap_day():
    assert one_year_after(date(2028, 2, 29)) == date(2029, 2, 28)


def test_describe_weekly():
    assert describe("weekly", [0, 3], date(2026, 10, 12)) == "Hver mandag og torsdag"
    assert describe("weekly", [0, 2, 4], date(2026, 10, 12)) == "Hver mandag, onsdag og fredag"
    assert describe("weekly", [1], date(2026, 10, 13)) == "Hver tirsdag"


def test_describe_monthly():
    assert describe("monthly", [], date(2026, 10, 13)) == "Hver 2. tirsdag i måneden"
    assert describe("monthly", [], date(2026, 10, 29)) == "Sidste torsdag i måneden"


def test_weekly_every_second_week_counted_from_start_week():
    # Onsdag 30-09-2026, hver 2. uge mandag+onsdag. Startugen (28/9) tæller som uge 0,
    # så mandag 28/9 ligger før startdatoen og springes over.
    got = _weekly([0, 2], date(2026, 9, 30), end_count=4, interval=2)
    assert got == [date(2026, 9, 30), date(2026, 10, 12), date(2026, 10, 14), date(2026, 10, 26)]


def test_weekly_interval_one_is_default():
    assert _weekly([1], date(2026, 10, 13), end_count=2) == _weekly([1], date(2026, 10, 13), end_count=2, interval=1)


def test_describe_weekly_interval():
    assert describe("weekly", [0, 3], date(2026, 10, 12), interval=2) == "Hver 2. uge: mandag og torsdag"
    assert describe("weekly", [0, 3], date(2026, 10, 12), interval=1) == "Hver mandag og torsdag"
