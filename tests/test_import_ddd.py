import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from pathlib import Path
from datetime import date, datetime
from decimal import Decimal

import pytest

from database.models import ActivityStatus, PayPeriodStatus, AppUser, AgreementKind, Activity, Employee, Base
from parsers.ddd_parser import ParsedActivity
from calculators.pay_period import get_or_create_period_for_date
from routers.import_ddd import _import_activity, _process_import_results, decline_closed_period_import, DeclineClosedPeriodRequest, DeclinedCandidate
from conftest import make_activity


def _parsed(start, end, segments, pauses, is_likely_incomplete=False):
    return ParsedActivity(
        tachograph_card_number="X",
        start_time=start,
        end_time=end,
        availability_time_pct=Decimal("0"),
        rest_pause_pct=Decimal("0"),
        other_work_pct=Decimal("0"),
        driving_pct=Decimal("0"),
        source_file="test.ddd",
        pause_intervals=pauses,
        segments=segments,
        is_likely_incomplete=is_likely_incomplete,
    )


def test_older_incomplete_readout_does_not_erase_already_complete_shift(db, employee):
    """
    En vagt er allerede importeret fuldt ud (fx fra en senere kortudlæsning,
    der pga. mappesortering blev behandlet FØRST). Genimporteres en ÆLDRE,
    ufuldstændig udlæsning af den samme vagt (kortere sluttidspunkt, ingen
    pause fundet endnu), må den ikke slette de allerede kendte pauser/segmenter.
    """
    start = datetime(2026, 8, 3, 5, 45)
    full_end = datetime(2026, 8, 3, 14, 30)
    full_segments = [
        (datetime(2026, 8, 3, 5, 45), datetime(2026, 8, 3, 11, 16), "work"),
        (datetime(2026, 8, 3, 11, 16), datetime(2026, 8, 3, 11, 41), "rest"),
        (datetime(2026, 8, 3, 11, 41), full_end, "driving"),
    ]
    full_pauses = [(datetime(2026, 8, 3, 11, 16), datetime(2026, 8, 3, 11, 41))]
    act = make_activity(db, employee, start=start, end=full_end, status=ActivityStatus.pending)
    act.segments = [[s.isoformat(), e.isoformat(), n] for s, e, n in full_segments]
    act.pause_intervals = [[s.isoformat(), e.isoformat()] for s, e in full_pauses]
    db.commit()

    incomplete_end = datetime(2026, 8, 3, 8, 8)
    incomplete = _parsed(
        start, incomplete_end,
        segments=[(start, incomplete_end, "work")],
        pauses=[],
        is_likely_incomplete=True,
    )

    _import_activity(incomplete, db, employee)
    db.refresh(act)

    assert act.end_time == full_end
    assert act.pause_intervals == [[s.isoformat(), e.isoformat()] for s, e in full_pauses]
    assert len(act.segments) == len(full_segments)


def test_later_more_complete_readout_still_extends_shift(db, employee):
    """Modsat tilfælde skal stadig virke: en SENERE, mere komplet udlæsning
    (længere sluttidspunkt) skal stadig udvide vagten og tilføje dens nye
    segmenter/pauser, uden at røre allerede gemte segmenter før cutoff."""
    start = datetime(2026, 8, 3, 5, 45)
    partial_end = datetime(2026, 8, 3, 8, 8)
    act = make_activity(db, employee, start=start, end=partial_end, status=ActivityStatus.pending)
    act.segments = [[start.isoformat(), partial_end.isoformat(), "work"]]
    act.pause_intervals = []
    db.commit()

    full_end = datetime(2026, 8, 3, 14, 30)
    complete = _parsed(
        start, full_end,
        segments=[
            (start, partial_end, "work"),
            (partial_end, datetime(2026, 8, 3, 11, 16), "work"),
            (datetime(2026, 8, 3, 11, 16), datetime(2026, 8, 3, 11, 41), "rest"),
            (datetime(2026, 8, 3, 11, 41), full_end, "driving"),
        ],
        pauses=[(datetime(2026, 8, 3, 11, 16), datetime(2026, 8, 3, 11, 41))],
    )

    result, _ = _import_activity(complete, db, employee)
    db.refresh(act)

    assert result == "updated"
    assert act.end_time == full_end
    assert len(act.pause_intervals) == 1


def test_corrected_earlier_start_time_extends_existing_activity_not_duplicates(db, employee):
    """
    Reproducerer Mikkel Hørlin 2/9-2026: aktiviteten blev oprindeligt
    importeret med start 07:02 (en parser-bug droppede en 8 min indledende
    hvil). Efter parser-rettelsen beregnes samme vagt nu korrekt til at
    starte 06:54. En genimport skal finde og OPDATERE den eksisterende
    aktivitet (samme vagt, blot et rettet starttidspunkt) – ikke oprette en
    ny, overlappende duplikat-aktivitet.
    """
    old_start = datetime(2026, 9, 2, 7, 2)
    end = datetime(2026, 9, 2, 14, 49)
    act = make_activity(db, employee, start=old_start, end=end, status=ActivityStatus.pending)
    act.segments = [[old_start.isoformat(), end.isoformat(), "driving"]]
    act.pause_intervals = []
    db.commit()

    corrected_start = datetime(2026, 9, 2, 6, 54)
    corrected = _parsed(
        corrected_start, end,
        segments=[
            (corrected_start, old_start, "rest"),
            (old_start, end, "driving"),
        ],
        pauses=[(corrected_start, old_start)],
    )

    result, _ = _import_activity(corrected, db, employee)
    db.refresh(act)

    assert result == "updated"
    assert act.start_time == corrected_start
    assert act.pause_intervals == [[corrected_start.isoformat(), old_start.isoformat()]]
    assert len(act.segments) == 2
    assert db.query(Activity).filter(Activity.employee_id == employee.id).count() == 1


def test_corrected_shorter_end_time_shrinks_pending_activity(db, employee):
    """
    Reproducerer Jesper Frederiksen 24/8-2026: en .ddd-fil indeholdt to
    modstridende dags-records for samme dato (se
    ddd_parser._find_all_daily_records), og den forkerte (kørsel uafbrudt til
    23:24) blev oprindeligt importeret. Efter parser-rettelsen beregnes samme
    vagt nu korrekt til at slutte 16:10. En genimport skal kunne RETTE den
    stadig afventende aktivitet til den kortere, korrekte tid – ikke kun
    udvide den.
    """
    start = datetime(2026, 8, 24, 5, 49)
    wrong_end = datetime(2026, 8, 24, 23, 24)
    act = make_activity(db, employee, start=start, end=wrong_end, status=ActivityStatus.pending)
    act.segments = [[start.isoformat(), wrong_end.isoformat(), "driving"]]
    act.pause_intervals = []
    db.commit()

    correct_end = datetime(2026, 8, 24, 16, 10)
    corrected = _parsed(
        start, correct_end,
        segments=[(start, correct_end, "driving")],
        pauses=[],
    )

    result, _ = _import_activity(corrected, db, employee)
    db.refresh(act)

    assert result == "updated"
    assert act.end_time == correct_end
    assert act.segments == [[start.isoformat(), correct_end.isoformat(), "driving"]]


def test_corrected_shorter_end_time_does_not_shrink_approved_activity(db, employee):
    """En allerede godkendt aktivitet må ikke gøres kortere af en genimport –
    brugeren har taget stilling til netop den (længere) periode. I stedet for
    at røre den godkendte aktivitet, skal genimporten oprette en helt ny,
    separat (pending) linje for dagen med den opdaterede vagt – også når
    starttidspunktet er uændret: det unikke indeks omfatter kun
    'pending'-rækker, så en ny pending-linje kan sagtens have samme
    starttidspunkt som den godkendte (bekræftet 2026-09-07)."""
    start = datetime(2026, 8, 24, 5, 49)
    wrong_end = datetime(2026, 8, 24, 23, 24)
    act = make_activity(db, employee, start=start, end=wrong_end, status=ActivityStatus.approved)
    act.segments = [[start.isoformat(), wrong_end.isoformat(), "driving"]]
    act.pause_intervals = []
    db.commit()

    correct_end = datetime(2026, 8, 24, 16, 10)
    corrected = _parsed(
        start, correct_end,
        segments=[(start, correct_end, "driving")],
        pauses=[],
    )

    result, _ = _import_activity(corrected, db, employee)
    db.refresh(act)

    assert act.end_time == wrong_end
    assert act.status == ActivityStatus.approved
    assert result == "new"

    all_acts = db.query(Activity).filter(Activity.employee_id == employee.id).all()
    assert len(all_acts) == 2
    new_line = next(a for a in all_acts if a.id != act.id)
    assert new_line.start_time == start
    assert new_line.end_time == correct_end
    assert new_line.status == ActivityStatus.pending


def test_corrected_earlier_start_time_on_approved_activity_creates_new_line(db, employee):
    """Viser en genimport en anden (fx tidligere) start end den, der allerede
    er godkendt, må den godkendte aktivitet stadig ikke røres – en ny,
    separat (pending) linje for dagen oprettes med den opdaterede vagt."""
    old_start = datetime(2026, 8, 24, 6, 30)
    end = datetime(2026, 8, 24, 16, 10)
    act = make_activity(db, employee, start=old_start, end=end, status=ActivityStatus.approved)
    act.segments = [[old_start.isoformat(), end.isoformat(), "driving"]]
    act.pause_intervals = []
    db.commit()

    corrected_start = datetime(2026, 8, 24, 5, 49)
    corrected = _parsed(
        corrected_start, end,
        segments=[(corrected_start, end, "driving")],
        pauses=[],
    )

    result, _ = _import_activity(corrected, db, employee)
    db.refresh(act)

    assert act.start_time == old_start
    assert act.status == ActivityStatus.approved
    assert result == "new"

    all_acts = db.query(Activity).filter(Activity.employee_id == employee.id).all()
    assert len(all_acts) == 2
    new_line = next(a for a in all_acts if a.id != act.id)
    assert new_line.start_time == corrected_start
    assert new_line.end_time == end
    assert new_line.status == ActivityStatus.pending


def test_extended_end_time_does_not_reopen_deactivated_activity(db, employee):
    """En deaktiveret aktivitet må hverken udvides eller genåbnes til pending
    af en genimport, selvom den nye udlæsning viser et senere sluttidspunkt –
    en tidligere "udvid og genåbn"-regel fortrød utilsigtet manuel oprydning
    af kendte duplikater (bekræftet 2026-09-07). I stedet oprettes en ny,
    separat (pending) linje for dagen med den fulde, opdaterede vagt."""
    start = datetime(2026, 6, 3, 6, 4)
    old_end = datetime(2026, 6, 3, 12, 6)
    act = make_activity(db, employee, start=start, end=old_end, status=ActivityStatus.deactivated)
    act.segments = [[start.isoformat(), old_end.isoformat(), "driving"]]
    act.pause_intervals = []
    db.commit()

    new_end = datetime(2026, 6, 3, 13, 30)
    updated = _parsed(
        start, new_end,
        segments=[(start, new_end, "driving")],
        pauses=[],
    )

    result, _ = _import_activity(updated, db, employee)
    db.refresh(act)

    assert act.end_time == old_end
    assert act.status == ActivityStatus.deactivated
    assert result == "new"

    all_acts = db.query(Activity).filter(Activity.employee_id == employee.id).all()
    assert len(all_acts) == 2
    new_line = next(a for a in all_acts if a.id != act.id)
    assert new_line.start_time == start
    assert new_line.end_time == new_end
    assert new_line.status == ActivityStatus.pending


def test_unchanged_readout_of_approved_activity_does_not_create_new_line(db, employee):
    """Genimporterer man præcis den samme vagt (ingen ny information), skal
    der IKKE oprettes en ny linje – kun rigtige ændringer i tid/segmenter
    udløser en ny linje for en godkendt/deaktiveret aktivitet."""
    start = datetime(2026, 8, 24, 5, 49)
    end = datetime(2026, 8, 24, 16, 10)
    act = make_activity(db, employee, start=start, end=end, status=ActivityStatus.approved)
    act.segments = [[start.isoformat(), end.isoformat(), "driving"]]
    act.pause_intervals = []
    db.commit()

    same = _parsed(
        start, end,
        segments=[(start, end, "driving")],
        pauses=[],
    )

    result, _ = _import_activity(same, db, employee)

    assert result == "skipped_duplicate"
    assert db.query(Activity).filter(Activity.employee_id == employee.id).count() == 1


def test_reimport_prefers_line_whose_original_times_overlap_over_manually_stretched_line(db, employee):
    """
    Reproducerer Mathias Hardon 24/9-2026: en dag med to tachograf-linjer
    (morgen 06:24-08:49 og eftermiddag 13:48-19:05) blev slået sammen manuelt
    ved at deaktivere morgenlinjen og trække eftermiddagslinjens START frem
    til 06:00, før den blev godkendt. Den udvidede linje overlapper nu
    morgenvagten med sine NUVÆRENDE tider, men ikke med sine OPRINDELIGE.
    En genimport af den uændrede morgenvagt skal matche den deaktiverede
    (identiske) morgenlinje – ikke den udvidede eftermiddagslinje, hvis
    oprindelige tider ikke passer og derfor udløste en ny dublet-linje.
    """
    m_start, m_end = datetime(2026, 9, 24, 6, 24), datetime(2026, 9, 24, 8, 49)
    a_start, a_end = datetime(2026, 9, 24, 13, 48), datetime(2026, 9, 24, 19, 5)

    stretched = make_activity(db, employee, start=datetime(2026, 9, 24, 6, 0), end=a_end,
                              status=ActivityStatus.approved)
    stretched.original_start_time = a_start
    stretched.original_end_time = a_end
    stretched.segments = [[a_start.isoformat(), a_end.isoformat(), "driving"]]
    stretched.pause_intervals = []

    morning = make_activity(db, employee, start=m_start, end=m_end, status=ActivityStatus.deactivated)
    morning.segments = [[m_start.isoformat(), m_end.isoformat(), "work"]]
    morning.pause_intervals = []
    db.commit()

    result, _ = _import_activity(
        _parsed(m_start, m_end, segments=[(m_start, m_end, "work")], pauses=[]), db, employee
    )
    assert result == "skipped_duplicate"

    result, _ = _import_activity(
        _parsed(a_start, a_end, segments=[(a_start, a_end, "driving")], pauses=[]), db, employee
    )
    assert result == "skipped_duplicate"

    db.refresh(stretched)
    assert stretched.start_time == datetime(2026, 9, 24, 6, 0)
    assert db.query(Activity).filter(Activity.employee_id == employee.id).count() == 2


def test_stale_incomplete_reread_of_deactivated_activity_does_not_create_new_line(db, employee):
    """
    Reproducerer Alexander B. Knudsen 11/9-2026: en vagt blev først importeret
    ufuldstændigt (kortet læst midt i vagten), senere genindlæst fuldt og
    derefter deaktiveret (brugeren erstattede den med en manuel linje). Den
    gamle, ufuldstændige .ddd-fil ligger stadig i ddd_input/ og bliver
    genparset ved hver eneste geninport (scan_ddd_folder() aldersfiltrerer
    kun på filens mtime, ikke på om den allerede er importeret) – uden at
    tilføje NOGEN ny information ift. den allerede afgjorte, fulde vagt.
    Det må ikke starte en ny konkurrerende linje hver gang.
    """
    start = datetime(2026, 9, 11, 6, 51)
    cutoff = datetime(2026, 9, 11, 8, 57)
    full_end = datetime(2026, 9, 11, 9, 55)
    full_segments = [
        (start, datetime(2026, 9, 11, 7, 23), "work"),
        (datetime(2026, 9, 11, 7, 23), datetime(2026, 9, 11, 7, 47), "driving"),
        (datetime(2026, 9, 11, 7, 47), cutoff, "work"),
        (cutoff, full_end, "driving"),
    ]
    act = make_activity(db, employee, start=start, end=full_end, status=ActivityStatus.deactivated)
    act.segments = [[s.isoformat(), e.isoformat(), n] for s, e, n in full_segments]
    act.pause_intervals = []
    db.commit()

    # Samme kort, læst midt i vagten – segmenterne er et rent præfiks af de
    # allerede kendte (grænsen falder præcis på en segmentovergang, som en
    # tachograf-udlæsning altid vil gøre).
    stale_incomplete = _parsed(
        start, cutoff,
        segments=full_segments[:3],
        pauses=[],
        is_likely_incomplete=True,
    )

    result, _ = _import_activity(stale_incomplete, db, employee)
    db.refresh(act)

    assert result == "skipped_duplicate"
    assert act.end_time == full_end
    assert act.status == ActivityStatus.deactivated
    assert db.query(Activity).filter(Activity.employee_id == employee.id).count() == 1


def test_legacy_corrected_segment_without_recorded_original_still_creates_one_more_line(db, employee):
    """
    Reproducerer Alexander B. Knudsen og Claus Ulrik Nicolaisen 9/9-2026: en
    aktivitet blev godkendt med et manuelt rettet segment (pause->arbejde, 4.
    element bevarer originalen, jf. correct_segment i activities.py) FØR
    original_segments-feltet fandtes, så ingen baseline blev fanget for netop
    DEN rettelse. Én sidste genimport opretter derfor stadig én ny linje her –
    kendt begrænsning, kræver et engangs-databackfill af original_segments for
    allerede eksisterende rettede aktiviteter (rekonstruerbart fra 4.
    element). Fra og med denne linje bliver rettet (fx via correct_segment
    igen på den nye linje), fanges original_segments dog fremover automatisk,
    jf. test_manually_corrected_segment_survives_reimport_via_original_segments
    nedenfor.
    """
    start = datetime(2026, 9, 9, 6, 25)
    end = datetime(2026, 9, 9, 13, 46)
    act = make_activity(db, employee, start=start, end=end, status=ActivityStatus.approved)
    rest_end = datetime(2026, 9, 9, 6, 26)
    act.segments = [
        [start.isoformat(), rest_end.isoformat(), "work", "rest"],
        [rest_end.isoformat(), end.isoformat(), "driving"],
    ]
    act.pause_intervals = []
    db.commit()

    same_source = _parsed(
        start, end,
        segments=[
            (start, rest_end, "rest"),
            (rest_end, end, "driving"),
        ],
        pauses=[(start, rest_end)],
    )

    result, _ = _import_activity(same_source, db, employee)
    db.refresh(act)

    assert result == "new"
    assert act.status == ActivityStatus.approved
    assert db.query(Activity).filter(Activity.employee_id == employee.id).count() == 2


def test_manually_corrected_segment_survives_reimport_via_original_segments(db, employee):
    """Samme scenarie som ovenfor, men original_segments ER sat (rettelsen
    skete via correct_segment EFTER dette felt blev indført) – skal opføre sig
    identisk: reimport af uændret kildedata må stadig ikke skabe en duplikat."""
    start = datetime(2026, 9, 9, 6, 25)
    end = datetime(2026, 9, 9, 13, 46)
    act = make_activity(db, employee, start=start, end=end, status=ActivityStatus.approved)
    rest_end = datetime(2026, 9, 9, 6, 26)
    original = [
        [start.isoformat(), rest_end.isoformat(), "rest"],
        [rest_end.isoformat(), end.isoformat(), "driving"],
    ]
    act.original_segments = original
    act.segments = [
        [start.isoformat(), rest_end.isoformat(), "work", "rest"],
        [rest_end.isoformat(), end.isoformat(), "driving"],
    ]
    act.pause_intervals = []
    db.commit()

    same_source = _parsed(
        start, end,
        segments=[
            (start, rest_end, "rest"),
            (rest_end, end, "driving"),
        ],
        pauses=[],
    )

    result, _ = _import_activity(same_source, db, employee)
    db.refresh(act)

    assert result == "skipped_duplicate"
    assert db.query(Activity).filter(Activity.employee_id == employee.id).count() == 1


def test_genuinely_different_segments_on_approved_activity_still_creates_new_line(db, employee):
    """En reel afvigelse i segmenterne (ikke bare en tidligere manuel rettelse)
    skal stadig udløse en ny linje, præcis som for tid – original_segments må
    ikke skjule ægte nye oplysninger fra en senere/mere fuldstændig udlæsning."""
    start = datetime(2026, 9, 9, 6, 25)
    end = datetime(2026, 9, 9, 13, 46)
    act = make_activity(db, employee, start=start, end=end, status=ActivityStatus.approved)
    act.segments = [[start.isoformat(), end.isoformat(), "driving"]]
    act.pause_intervals = []
    db.commit()

    pause_start = datetime(2026, 9, 9, 10, 0)
    pause_end = datetime(2026, 9, 9, 10, 15)
    different = _parsed(
        start, end,
        segments=[
            (start, pause_start, "driving"),
            (pause_start, pause_end, "rest"),
            (pause_end, end, "driving"),
        ],
        pauses=[(pause_start, pause_end)],
    )

    result, _ = _import_activity(different, db, employee)
    db.refresh(act)

    assert result == "new"
    assert act.status == ActivityStatus.approved
    assert db.query(Activity).filter(Activity.employee_id == employee.id).count() == 2


def test_corrected_shorter_end_time_does_not_shrink_split_activity(db, employee):
    """En aktivitet der er en af de to dele af et split må ikke gøres kortere
    af en genimport – brugeren har bevidst omfordelt tiden mellem de to
    dele."""
    start = datetime(2026, 8, 24, 5, 49)
    wrong_end = datetime(2026, 8, 24, 23, 24)
    act = make_activity(db, employee, start=start, end=wrong_end, status=ActivityStatus.pending)
    act.segments = [[start.isoformat(), wrong_end.isoformat(), "driving"]]
    act.pause_intervals = []
    act.parent_activity_id = 999
    act.split_part = 2
    db.commit()

    correct_end = datetime(2026, 8, 24, 16, 10)
    corrected = _parsed(
        start, correct_end,
        segments=[(start, correct_end, "driving")],
        pauses=[],
    )

    result, _ = _import_activity(corrected, db, employee)
    db.refresh(act)

    assert act.end_time == wrong_end


def _test_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_closed_period_candidates_deduped_across_files(db, employee):
    """
    Reproducerer den rapporterede fejl: samme vagt findes i flere .ddd-filer
    (typisk fra flere kortudlæsninger over tid), og vagten falder i en
    allerede lukket lønperiode. closed_period_candidates må kun indeholde
    ÉT eksemplar af vagten, ikke ét pr. fil den er fundet i – ellers ser
    brugeren den samme vagt flere gange i bekræftelses-popup'en.
    """
    employee.tachograph_card_number = "TESTCARD1"
    db.commit()

    closed_date = datetime(2026, 7, 15).date()
    period = get_or_create_period_for_date(closed_date, db)
    period.status = PayPeriodStatus.closed
    db.commit()

    start = datetime(2026, 7, 15, 5, 27)
    end = datetime(2026, 7, 15, 16, 46)
    act1 = _parsed(start, end, segments=[(start, end, "work")], pauses=[])
    act2 = _parsed(start, end, segments=[(start, end, "work")], pauses=[])
    act1.tachograph_card_number = act2.tachograph_card_number = "TESTCARD1"

    results = [(Path("file_a.ddd"), [act1]), (Path("file_b.ddd"), [act2])]

    result = _process_import_results(results, [], _test_user(), db)

    assert len(result["closed_period_candidates"]) == 1


def test_decline_closed_period_import_handles_duplicate_items_in_same_request(db, employee):
    """
    Reproducerer den rapporterede fejl: brugeren trykker "Nej, spring over"
    på en liste hvor samme vagt (samme medarbejder+starttid) optræder to
    gange. Uden fix crasher dette med en IntegrityError på det unikke index
    (employee_id, start_time), og HELE afvisningen mislykkes – ingen af
    vagterne huskes som sprunget over.
    """
    start = datetime(2026, 7, 15, 5, 27)
    end = datetime(2026, 7, 15, 16, 46)
    body = DeclineClosedPeriodRequest(items=[
        DeclinedCandidate(employee_id=employee.id, start_time=start.isoformat(), end_time=end.isoformat()),
        DeclinedCandidate(employee_id=employee.id, start_time=start.isoformat(), end_time=end.isoformat()),
    ])

    # Produktionens SessionLocal bruger autoflush=False (database/session.py) –
    # matcher det her, så testen rammer den samme betingelse som i praksis.
    db.autoflush = False
    result = decline_closed_period_import(body, _test_user(), db)

    assert result["declined"] == 1


