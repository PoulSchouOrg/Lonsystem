"""
Opretter 10 fiktive testmedarbejdere med varierede overenskomsttyper,
timefordelinger og aktiviteter i perioden 1/6-14/6 2026.
Kør: python seed_testdata.py
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from database.session import get_db, init_db
from database.models import (
    Activity, ActivitySource, ActivityStatus, ActivityType,
    AgreementKind, Employee,
)
from calculators.pay_period import get_or_create_period_for_date

init_db()
db = next(get_db())

FIVE_DAY_7 = {"even": [7, 7, 7, 7, 7, 0, 0], "odd": [7, 7, 7, 7, 7, 0, 0]}
FIVE_DAY_74 = {"even": [7.4, 7.4, 7.4, 7.4, 7.4, 0, 0], "odd": [7.4, 7.4, 7.4, 7.4, 7.4, 0, 0]}
FOUR_DAY = {"even": [9, 9, 9, 9, 0, 0, 0], "odd": [9, 9, 9, 9, 0, 0, 0]}

# (lønnr, fornavn, efternavn, overenskomsttype, kort, schedule, mønster)
# mønster styrer hvilke slags dage der genereres
EMPLOYEES = [
    ("002", "Allan Redin", "Nykov", "Chauffør. 9 mdr anciennitet", "DK00000178901011", FIVE_DAY_7, "early_long"),
    ("003", "Anders Jersild", "Nielsen", "Chauffør", "DK00000178901012", FIVE_DAY_7, "evening"),
    ("004", "Andreas", "Lentz", "Chauffør. Faglært", "DK00000178901013", FIVE_DAY_74, "sick"),
    ("005", "Bo", "Madsen", "Chauffør med kvalifikationstillæg", "DK00000178901014", FIVE_DAY_7, "normal"),
    ("006", "Carsten", "Holm", "Chauffør med kvalifikationstillæg. 9 mdr anciennitet", "DK00000178901015", FIVE_DAY_7, "night"),
    ("007", "Dennis", "Iversen", "Chauffør under oplæring", "DK00000178901016", FIVE_DAY_7, "short"),
    ("008", "Erik", "Skov", "Specialarbejder uden andre tillæg", "DK00000178901017", FOUR_DAY, "long4"),
    ("009", "Frank", "Würtz", "Chauffør. 9 mdr anciennitet", "DK00000178901018", FIVE_DAY_7, "mixed"),
    ("010", "Gert", "Albrechtsen", "Lager- og terminalmedarbejder. Provinsen", "DK00000178901019", FIVE_DAY_74, "normal"),
    ("011", "Henrik", "Dahl", "Flyttearbejdere", "DK00000178901020", FIVE_DAY_7, "vacation"),
]

PERIOD_START = date(2026, 6, 1)  # mandag

def add_activity(emp, d, start_h, start_m, end_h, end_m, status, source=ActivitySource.tachograph,
                 atype=ActivityType.normal, comment=None, next_day_end=False, pauses=None):
    """pauses: liste af (start_h, start_m, slut_h, slut_m) samme dag."""
    start = datetime(d.year, d.month, d.day, start_h, start_m)
    end_date = d + timedelta(days=1) if next_day_end else d
    end = datetime(end_date.year, end_date.month, end_date.day, end_h, end_m)
    period = get_or_create_period_for_date(d, db)
    pause_intervals = [
        [datetime(d.year, d.month, d.day, ph1, pm1).isoformat(),
         datetime(d.year, d.month, d.day, ph2, pm2).isoformat()]
        for ph1, pm1, ph2, pm2 in (pauses or [])
    ]

    # Generér realistiske hændelsessegmenter: arbejdstid skiftevis kørsel/andet
    # arbejde i ~45-min blokke, pauser som "rest"
    segments = []
    if atype == ActivityType.normal:
        boundaries = [start]
        for ps, pe in [(datetime.fromisoformat(x[0]), datetime.fromisoformat(x[1]))
                       for x in pause_intervals]:
            boundaries += [ps, pe]
        boundaries.append(end)
        for j in range(0, len(boundaries) - 1, 2):
            w_start, w_end = boundaries[j], boundaries[j + 1]
            cur = w_start
            toggle = True
            while cur < w_end:
                nxt = min(cur + timedelta(minutes=45), w_end)
                segments.append([cur.isoformat(), nxt.isoformat(),
                                 "driving" if toggle else "work"])
                toggle = not toggle
                cur = nxt
            if j + 2 < len(boundaries):
                segments.append([boundaries[j + 1].isoformat(),
                                 boundaries[j + 2].isoformat(), "rest"])
    db.add(Activity(
        employee_id=emp.id,
        pay_period_id=period.id,
        source=source,
        activity_type=atype,
        start_time=start,
        end_time=end,
        driving_pct=55, other_work_pct=20, availability_time_pct=10, rest_pause_pct=15,
        pause_intervals=pause_intervals,
        segments=segments,
        status=status,
        approved_by="STS" if status == ActivityStatus.approved else None,
        approved_at=datetime.now() if status == ActivityStatus.approved else None,
        comment=comment,
    ))


created = 0
for nr, fn, ln, agreement, card, schedule, pattern in EMPLOYEES:
    if db.query(Employee).filter(Employee.employee_number == nr).first():
        print(f"Springer over (findes): {nr} {fn} {ln}")
        continue
    emp = Employee(
        employee_number=nr,
        tachograph_card_number=card,
        first_name=fn, last_name=ln,
        address="Testvej 1", postal_code="2600",
        email=f"{fn.split()[0].lower()}@poulschou-test.dk",
        mobile="12345678",
        agreement_kind=AgreementKind.hourly_fixed,
        agreement_type=agreement,
        fuldloennet=True, active=True,
        hire_date=date(2025, 3, 1) if "anciennitet" in agreement else date(2026, 4, 1),
        termination_date=date(9999, 12, 31),
        work_schedule=schedule,
    )
    db.add(emp)
    db.flush()
    created += 1

    P = ActivityStatus.pending
    A = ActivityStatus.approved
    D = ActivityStatus.deactivated
    M = ActivitySource.manual

    workdays = [PERIOD_START + timedelta(days=i) for i in range(14)
                if (PERIOD_START + timedelta(days=i)).weekday() < 5]

    if pattern == "early_long":
        # Tidlige morgener, lange dage, en deaktiveret + manuel rettelse
        for i, d in enumerate(workdays):
            if i == 2:
                add_activity(emp, d, 5, 38, 18, 49, D, comment="Fejl i tachograf")
                add_activity(emp, d, 5, 38, 19, 16, A, source=M, comment="Rettet efter dagsseddel")
            elif i % 3 == 0:
                # Pause 12:00-12:30 (normal-tid) og 18:45-19:00 (i 18-21-tillægget)
                add_activity(emp, d, 5, 47, 18, 30, A, pauses=[(12, 0, 12, 30)])
            else:
                add_activity(emp, d, 5, 35, 16, 48, P, pauses=[(11, 30, 12, 0)])
    elif pattern == "evening":
        for i, d in enumerate(workdays):
            if i == 1:
                add_activity(emp, d, 18, 9, 2, 30, D, next_day_end=True, comment="Start fra dagen før")
                add_activity(emp, d, 18, 9, 23, 45, P, source=M)
            else:
                # Pause 19:30-20:00 ligger i 18-21-tillægget og fratrækkes dér
                add_activity(emp, d, 15, 32, 23, 50, A if i % 2 == 0 else P, pauses=[(19, 30, 20, 0)])
    elif pattern == "sick":
        for i, d in enumerate(workdays):
            if i < 6:
                add_activity(emp, d, 8, 0, 15, 24, A, source=M, atype=ActivityType.fri, comment="Sygedag")
            else:
                add_activity(emp, d, 6, 30, 14, 0, P)
    elif pattern == "normal":
        for i, d in enumerate(workdays):
            add_activity(emp, d, 6, 58 if i % 2 else 2, 14, 30 + i % 20, A if i % 3 else P)
    elif pattern == "night":
        for i, d in enumerate(workdays[:8]):
            add_activity(emp, d, 21, 15, 6, 40, P if i % 2 else A, next_day_end=True)
    elif pattern == "short":
        # Under 4 timer – kræver kommentar ved godkendelse
        for i, d in enumerate(workdays):
            if i % 2 == 0:
                add_activity(emp, d, 9, 0, 12, 15, P)
            else:
                add_activity(emp, d, 7, 0, 15, 30, A)
    elif pattern == "long4":
        for d in workdays:
            if d.weekday() < 4:
                add_activity(emp, d, 6, 0, 17, 45, P)
    elif pattern == "mixed":
        for i, d in enumerate(workdays):
            if i == 3:
                add_activity(emp, d, 8, 0, 16, 0, A, source=M, atype=ActivityType.afspadsering)
            elif i == 4:
                add_activity(emp, d, 14, 41, 22, 30, A)
            elif i % 2 == 0:
                add_activity(emp, d, 4, 10, 14, 5, P)
            else:
                add_activity(emp, d, 16, 22, 23, 59, D, comment="Dobbeltregistrering")
    elif pattern == "vacation":
        for i, d in enumerate(workdays):
            if i < 5:
                add_activity(emp, d, 8, 0, 15, 24, A, source=M, atype=ActivityType.ferie)
            else:
                add_activity(emp, d, 7, 15, 15, 45, P)

    print(f"Oprettet: {nr} {fn} {ln} ({agreement}, mønster: {pattern})")

# ── Elever til elevløn-trin (2026-10-06) ─────────────────────────────────────
# Datoer regnes ud fra i dag, så scenarierne altid er aktuelle:
# 012 skifter til sidste år om ca. 3 uger (advarsel), 013 er gået ind i sidste år
# men har stadig næstsidste-typen (mulig fejl), 014 er midt i tredjesidste år,
# 015 er voksenelev (ingen trin) og 016 er EGU-elev (ingen trin).
def _years_from(d, years, days=0):
    try:
        out = d.replace(year=d.year + years)
    except ValueError:  # 29/2
        out = d.replace(year=d.year + years, day=28)
    return out + timedelta(days=days)

TODAY = date.today()
ELEVER = [
    ("012", "Ida", "Elevsen", "Lærling (EUD) Næstsidsteår af lærerkontrakt", _years_from(TODAY, 1, 20), False),
    ("013", "Jonas", "Elevsen", "Lærling (EUD) Næstsidsteår af lærerkontrakt", _years_from(TODAY, 1, -10), False),
    ("014", "Karla", "Elevsen", "Lærling (EUD) Tredjesidste år af lærerkontrakt", _years_from(TODAY, 2, 180), False),
    ("015", "Lars", "Voksenelev", "Chauffør", _years_from(TODAY, 1, 15), True),
    ("016", "Mia", "Egu", "EGU-elever", _years_from(TODAY, 1), False),
]
for nr, fn, ln, agreement, end, voksen in ELEVER:
    if db.query(Employee).filter(Employee.employee_number == nr).first():
        print(f"Springer over (findes): {nr} {fn} {ln}")
        continue
    db.add(Employee(
        employee_number=nr, tachograph_card_number=f"DK0000017890{nr}",
        first_name=fn, last_name=ln, address="Testvej 1", postal_code="2600",
        email=f"{fn.lower()}@poulschou-test.dk", mobile="12345678",
        agreement_kind=AgreementKind.hourly_fixed, agreement_type=agreement,
        fuldloennet=True, active=True, hire_date=_years_from(end, -3, 1),
        termination_date=date(9999, 12, 31), work_schedule=FIVE_DAY_7,
        elev=True, elev_start_date=_years_from(end, -2 if voksen else -3, 1), elev_end_date=end,
        voksenelev=voksen,
    ))
    created += 1
    print(f"Oprettet elev: {nr} {fn} {ln} ({agreement}, slut {end})")

db.commit()
db.close()
print(f"\n{created} testmedarbejdere oprettet (aktiviteter i perioden 1/6-14/6 2026).")
