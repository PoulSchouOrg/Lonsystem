"""
Overtidsberegning efter kravdokumentet "Ønsker til opsætning+funktioner".

Tre tillægstyper (satser fra "Overtid satser.xlsx"):
- "Overtid 1 time før":      arbejde kl. 05-06
- "Overtid 1-3 timer efter": arbejde kl. 18-21, samt timer ud over normaltid
                             i tidsrummet kl. 06-18
- "Øvrigt overtid":          arbejde kl. 21-05, samt overtidstimer ud over
                             de første 3 (bekræftet af bruger 10/6-2026)

Normaltid pr. dag kommer fra medarbejderens timefordeling (lige/ulige uger).
Alle arbejdstimer tæller med i normal_hours (kode 1), men de REGISTREREDE
normaltimer (7/7,5/8 t) kan kun forbruges i tidsrummet 06-18 – arbejde uden
for dette vindue (nat, "1 time før", aften) er altid rent tillæg og fortærer
ikke normaltids-loftet (bekræftet af bruger 2026-07-02).

Beregningen er daglig (pr. aktivitet).
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from calculators.rates_loader import load_overtime_rates
from calculators.vehicle_uses import split_by_vehicle

OT_BEFORE_KEY = "Overtid 1 time før"
OT_13_KEY = "Overtid 1-3 timer efter"
OT_EXTRA_KEY = "Øvrigt overtid"

OT_13_MAX = Decimal("3")  # maks. 3 timer i "Overtid 1-3 timer efter"


@dataclass
class OvertimeResult:
    total_hours: Decimal = Decimal("0")
    normal_hours: Decimal = Decimal("0")      # uden tillæg
    ot_before_hours: Decimal = Decimal("0")   # Overtid 1 time før (05-06)
    ot_13_hours: Decimal = Decimal("0")       # Overtid 1-3 timer efter
    ot_extra_hours: Decimal = Decimal("0")    # Øvrigt overtid
    sh_kode8_hours: Decimal = Decimal("0")   # additiv supplement kode 8 på særlige dage
    sh_kode9_hours: Decimal = Decimal("0")   # additiv supplement kode 9 på særlige dage
    # Resterende normaltids-/OT13-loft EFTER denne aktivitet – videreføres til næste
    # aktivitet SAMME dag, når en dag er delt i flere godkendte aktiviteter, så loftet
    # deles for hele dagen i stedet for at blive nulstillet pr. aktivitet.
    normal_remaining_after: Decimal = Decimal("0")
    ot13_remaining_after: Decimal = Decimal("0")
    supplements: dict = field(default_factory=dict)
    # Timerne fordelt pr. KALENDERDAG de faktisk er arbejdet på – en vagt der
    # krydser midnat bidrager til to datoer her, selvom den regnes som ét
    # sammenhængende skift ovenfor (loftet er ikke pr.-dato nulstillet).
    # Bruges af Lønafregning til at vise timerne på de rigtige dage (bekræftet
    # af bruger 2026-09-09) uden at ændre selve tærskel-beregningen.
    by_date: dict = field(default_factory=dict)
    # Som by_date, men nøglet (dato, registreringsnummer) – kun udfyldt når
    # vagten er kørt i flere biler (vehicle_intervals angivet). Bruges af
    # Lønafregning til én linje pr. bil pr. dag (bekræftet af bruger 2026-09-30).
    by_date_vehicle: dict = field(default_factory=dict)

    def supplement_total(self) -> Decimal:
        return sum(self.supplements.values(), Decimal("0"))


def _window(dt: datetime) -> str:
    """Klassificér et tidspunkt efter tidsvindue."""
    h = dt.hour
    if 5 <= h < 6:
        return "before"      # 05-06
    if 6 <= h < 18:
        return "day"         # 06-18
    if 18 <= h < 21:
        return "evening"     # 18-21
    return "night"           # 21-05


def _new_bucket() -> dict:
    return {
        "normal": Decimal("0"), "ot_before": Decimal("0"),
        "ot_13": Decimal("0"), "ot_extra": Decimal("0"),
        "total_hours": Decimal("0"),
        "sh_kode8": Decimal("0"), "sh_kode9": Decimal("0"),
    }


def _allocate_to_vehicles(result, seg_start, seg_end, duration, parts, vehicle_intervals) -> None:
    """Fordeler ét allerede beregnet segment på bilerne i by_date_vehicle.

    Selve beregningen (totaler, loft, by_date) sker på de uændrede
    time-segmenter, så en opdeling pr. bil aldrig ændrer lønnen – heller ikke
    med en Decimal-afrundingsforskel. Segmentets timer (`parts`, i kronologisk
    prioritet: normaltid før OT 1-3 før Øvrig) tildeles bilerne i den
    rækkefølge de er kørt, så den bil der køres først også forbruger loftet
    først."""
    pieces = list(split_by_vehicle([(seg_start, seg_end)], vehicle_intervals))
    sub_durations = [Decimal(str((e - s).total_seconds())) / 3600 for s, e, _ in pieces]
    if sub_durations:
        sub_durations[-1] = duration - sum(sub_durations[:-1], Decimal("0"))
    remaining_parts = [[key, amount] for key, amount in parts]
    for (_, _, reg), sub in zip(pieces, sub_durations):
        bucket = result.by_date_vehicle.setdefault((seg_start.date(), reg), _new_bucket())
        bucket["total_hours"] += sub
        bucket["normal"] += sub
        left = sub
        for part in remaining_parts:
            if left <= 0:
                break
            take = min(left, part[1])
            if take <= 0:
                continue
            if part[0]:
                bucket[part[0]] += take
            part[1] -= take
            left -= take


def _segments(start: datetime, end: datetime):
    """Opdel ved hver hel time og midnat."""
    current = start
    while current < end:
        next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        seg_end = min(next_hour, end)
        yield current, seg_end
        current = seg_end


def _work_segments(work_intervals):
    """Time-opdelte segmenter for alle arbejdsintervaller (kronologisk)."""
    for w_start, w_end in work_intervals:
        yield from _segments(w_start, w_end)


def _subtract_pauses(
    start: datetime, end: datetime,
    pauses: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    """
    Returnér arbejdsintervaller = [start, end] minus pauseintervaller.
    Pausen fratrækkes dermed i det tidsrum, den faktisk afholdes.
    """
    work = [(start, end)]
    for p_start, p_end in sorted(pauses):
        new_work = []
        for w_start, w_end in work:
            if p_end <= w_start or p_start >= w_end:
                new_work.append((w_start, w_end))  # ingen overlap
                continue
            if p_start > w_start:
                new_work.append((w_start, p_start))
            if p_end < w_end:
                new_work.append((p_end, w_end))
        work = new_work
    return work


def calculate_overtime(
    start: datetime,
    end: datetime,
    normal_daily_hours: Decimal,
    pause_intervals: list[tuple[datetime, datetime]] | None = None,
    rates: dict | None = None,
    normal_remaining: Decimal | None = None,
    ot13_remaining: Decimal | None = None,
    next_day_normal_hours: Decimal | None = None,
    vehicle_intervals: list[tuple[datetime, datetime, str]] | None = None,
) -> OvertimeResult:
    """
    Beregn timefordelingen for én aktivitet (ét skift).
    normal_daily_hours: medarbejderens normaltid for den pågældende dag
    (fra timefordelingen, lige/ulige uge).
    pause_intervals: faktiske pauser – fratrækkes i det tidsrum de afholdes,
    så der ikke gives tillæg for tid, hvor der ikke arbejdes.
    normal_remaining/ot13_remaining: valgfrit resterende loft videreført fra en
    tidligere aktivitet SAMME dag (når dagen er delt i flere godkendte
    aktiviteter) – uden angivelse startes der forfra fra
    normal_daily_hours/OT_13_MAX.
    next_day_normal_hours: en vagt der krydser midnat splittes IKKE i separate
    aktiviteter (bekræftet 2026-07-02), men for medarbejdere med et DAGLIGT
    loft (hourly_fixed) skal OT-1-3-loftet nulstilles til friske 3 timer ved
    midnat for HVER kalenderdag, og normaltids-loftet skifter til den nye dags
    eget garanterede timetal – ellers bliver fx en lørdags-fortsættelse af en
    fredagsvagt fejlagtigt dækket af fredagens (ubrugte) normaltids-loft, selv
    om lørdag ikke har noget loft at forbruge (bekræftet af bruger 2026-08-17,
    jf. Jesper Rosengreen-sagen). Kun angivet af kaldere med et dagligt loft –
    ved None (fx den ugentlige 37t/5t-pulje for hourly_flexible) bevares det
    oprindelige loft helt uændret over midnat, som hidtil.
    vehicle_intervals: se calculators/vehicle_uses.py – de beregnede timer
    fordeles bagefter pr. bil i by_date_vehicle (_allocate_to_vehicles);
    selve beregningen er uændret.
    """
    result = OvertimeResult()
    if rates is None:
        rates = load_overtime_rates()

    normal_remaining = Decimal(str(normal_daily_hours)) if normal_remaining is None else normal_remaining
    ot13_remaining = OT_13_MAX if ot13_remaining is None else ot13_remaining

    work_intervals = _subtract_pauses(start, end, pause_intervals or [])

    active_date = start.date()

    for seg_start, seg_end in _work_segments(work_intervals):
        duration = Decimal(str((seg_end - seg_start).total_seconds())) / 3600
        if duration <= 0:
            continue

        if seg_start.date() != active_date:
            active_date = seg_start.date()
            if next_day_normal_hours is not None:
                normal_remaining = Decimal(str(next_day_normal_hours))
                ot13_remaining = OT_13_MAX

        result.total_hours += duration
        day_bucket = result.by_date.setdefault(seg_start.date(), {
            "normal": Decimal("0"), "ot_before": Decimal("0"),
            "ot_13": Decimal("0"), "ot_extra": Decimal("0"),
            "total_hours": Decimal("0"),
        })
        day_bucket["total_hours"] += duration

        window = _window(seg_start)

        # Alle arbejdede timer giver normal løn (kode 1). Tillæg er additive.
        result.normal_hours += duration
        day_bucket["normal"] += duration

        # Segmentets timer i kronologisk prioritet (til fordeling pr. bil):
        # (tillægsnøgle eller None, timer).
        parts: list = []
        if window == "night":
            # 21-05: Øvrigt overtid-tillæg. Registreret normaltid kan kun
            # forbruges i tidsrummet 06-18, så nattetimer fortærer ikke loftet.
            result.ot_extra_hours += duration
            day_bucket["ot_extra"] += duration
            parts = [("ot_extra", duration)]
        elif window == "before":
            # 05-06: "Overtid 1 time før" regnes separat og fortærer ikke
            # normaltids-loftet (bekræftet af bruger 2026-07-02).
            result.ot_before_hours += duration
            day_bucket["ot_before"] += duration
            parts = [("ot_before", duration)]
        elif window == "evening":
            # 18-21: OT 1-3-tillæg (op til 3 timer), derefter Øvrig-tillæg.
            # Ligger uden for 06-18, så det fortærer heller ikke normaltids-loftet.
            in_13 = min(duration, ot13_remaining)
            result.ot_13_hours += in_13
            day_bucket["ot_13"] += in_13
            ot13_remaining -= in_13
            overflow = duration - in_13
            parts = [("ot_13", in_13)]
            if overflow > 0:
                result.ot_extra_hours += overflow
                day_bucket["ot_extra"] += overflow
                parts.append(("ot_extra", overflow))
        else:
            # 06-18: forbruger normaltid; overtid ud over kap → supplement-tillæg
            as_normal = min(duration, normal_remaining)
            normal_remaining -= as_normal
            rest = duration - as_normal
            parts = [(None, as_normal)]
            if rest > 0:
                in_13 = min(rest, ot13_remaining)
                result.ot_13_hours += in_13
                day_bucket["ot_13"] += in_13
                ot13_remaining -= in_13
                overflow = rest - in_13
                parts.append(("ot_13", in_13))
                if overflow > 0:
                    result.ot_extra_hours += overflow
                    day_bucket["ot_extra"] += overflow
                    parts.append(("ot_extra", overflow))

        if vehicle_intervals:
            _allocate_to_vehicles(result, seg_start, seg_end, duration, parts, vehicle_intervals)

    result.supplements = {
        OT_BEFORE_KEY: result.ot_before_hours * rates.get(OT_BEFORE_KEY, Decimal("0")),
        OT_13_KEY:     result.ot_13_hours     * rates.get(OT_13_KEY,     Decimal("0")),
        OT_EXTRA_KEY:  result.ot_extra_hours  * rates.get(OT_EXTRA_KEY,  Decimal("0")),
    }
    result.normal_remaining_after = normal_remaining
    result.ot13_remaining_after = ot13_remaining
    return result


def calculate_flat_hours(
    start: datetime,
    end: datetime,
    pause_intervals: list[tuple[datetime, datetime]] | None = None,
    vehicle_intervals: list[tuple[datetime, datetime, str]] | None = None,
) -> OvertimeResult:
    """
    Bruges til medarbejdere med en Aftale-type uden for de to kendte nøgler
    (hourly_fixed/hourly_flexible, jf. AgreementKind i database/models.py) –
    ingen tillæg eller loft, kun rene arbejdstimer til normal sats.
    """
    result = OvertimeResult()
    work_intervals = _subtract_pauses(start, end, pause_intervals or [])
    for seg_start, seg_end in _work_segments(work_intervals):
        duration = Decimal(str((seg_end - seg_start).total_seconds())) / 3600
        if duration <= 0:
            continue
        result.total_hours += duration
        result.normal_hours += duration
        day_bucket = result.by_date.setdefault(seg_start.date(), {
            "normal": Decimal("0"), "ot_before": Decimal("0"),
            "ot_13": Decimal("0"), "ot_extra": Decimal("0"),
            "total_hours": Decimal("0"),
        })
        day_bucket["total_hours"] += duration
        day_bucket["normal"] += duration
        if vehicle_intervals:
            _allocate_to_vehicles(result, seg_start, seg_end, duration, [(None, duration)], vehicle_intervals)
    return result


def override_ot_extra_alle_timer(
    result: OvertimeResult, is_special_day: bool, rates: dict,
) -> OvertimeResult:
    """
    Særaftale (Employee.ot_extra_alle_timer): normal løn for alle arbejdstimer
    OG Øvrig overtid (kode 9) for alle arbejdstimer - aldrig Overtid 1-3 timer
    (kode 8). Kode 4/63 (SH-garanti) beregnes i compute_sh_hours() og påvirkes
    ikke af denne funktion.

    is_special_day=False (hverdag/lørdag, `result` fra calculate_flat_hours()):
    ot_extra_hours sættes til alle timer.
    is_special_day=True (søndag/helligdag, `result` fra
    calculate_special_day_overtime()): sh_kode8_hours nulstilles og
    sh_kode9_hours sættes til alle timer - normal_hours er i forvejen altid
    alle kørte timer for særlige dage.
    """
    result.ot_before_hours = Decimal("0")
    result.ot_13_hours = Decimal("0")
    if is_special_day:
        result.sh_kode8_hours = Decimal("0")
        result.sh_kode9_hours = result.total_hours
        for bucket in result.by_date_vehicle.values():
            bucket["sh_kode8"] = Decimal("0")
            bucket["sh_kode9"] = bucket["total_hours"]
    else:
        result.ot_extra_hours = result.total_hours
        result.supplements = {OT_EXTRA_KEY: result.ot_extra_hours * rates.get(OT_EXTRA_KEY, Decimal("0"))}
        for bucket in result.by_date.values():
            bucket["ot_extra"] = bucket["total_hours"]
        for bucket in result.by_date_vehicle.values():
            bucket["ot_before"] = Decimal("0")
            bucket["ot_13"] = Decimal("0")
            bucket["ot_extra"] = bucket["total_hours"]
    return result
