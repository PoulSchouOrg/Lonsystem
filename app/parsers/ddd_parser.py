"""
Custom parser for EU digital tachograph .ddd driver card files.
No external dependencies.

Format: EU Regulation 165/2014 / Commission Regulation 2016/799 Annex II.

Daily record structure (consecutive, variable length):
  2 bytes: previousRecordLength
  2 bytes: recordLength (total bytes incl. this 4-byte header)
  4 bytes: date (Unix timestamp, midnight UTC)
  2 bytes: dailyPresenceCounter
  2 bytes: activityDayDistance (km)
  N*2 bytes: ActivityChangeInfo records

ActivityChangeInfo (2 bytes, big-endian):
  bit 15:     slot (0=driver/chauffør, 1=co-driver/medchauffør)
  bit 14:     driverStatus (0=single, 1=crew)
  bit 13:     cardPresent
  bits 12-11: activity (00=rest, 01=availability, 10=work, 11=driving)
  bits 10-0:  minutes from midnight (0-1439), also relative to UTC midnight

Alle klokkeslæt i filen (dato og minutter) er UTC. Outputtet fra denne parser
konverteres til dansk lokal tid (Europe/Copenhagen, DST-korrekt) i _build_activities.
"""

import re
import struct
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

ACTIVITY_REST = 0
ACTIVITY_AVAILABILITY = 1
ACTIVITY_WORK = 2
ACTIVITY_DRIVING = 3

# Minimum record size: 4-byte header + date(4) + counter(2) + distance(2) = 12
MIN_RECORD_SIZE = 12
# Plausible timestamp range: 2020-01-01 to 2035-01-01
TS_MIN = 1577836800
TS_MAX = 2051222400

_UTC = ZoneInfo("UTC")
_COPENHAGEN = ZoneInfo("Europe/Copenhagen")


def _utc_to_local(dt: datetime) -> datetime:
    """Konverter en naiv UTC-datetime (fra filens rå tidsstempler) til naiv dansk lokal tid."""
    return dt.replace(tzinfo=_UTC).astimezone(_COPENHAGEN).replace(tzinfo=None)


@dataclass
class ParsedActivity:
    tachograph_card_number: str
    start_time: datetime
    end_time: datetime
    availability_time_pct: Decimal | None
    rest_pause_pct: Decimal | None
    other_work_pct: Decimal | None
    driving_pct: Decimal | None
    source_file: str
    vehicle_registration: str | None = None
    km_start: int | None = None
    km_end: int | None = None
    # Faktiske pauseintervaller (hvil/pause) mellem start og slut,
    # så pauser kan fratrækkes i det tidsrum de afholdes
    pause_intervals: list[tuple[datetime, datetime]] = None
    # Alle hændelsessegmenter: (start, slut, aktivitet) hvor aktivitet er
    # "rest" | "availability" | "work" | "driving"
    segments: list[tuple[datetime, datetime, str]] = None
    # Filen ser ud til at være hentet midt i vagten (0 km registreret den dag,
    # og dagen slutter ikke i hvil) – resten af dagen mangler formentlig
    is_likely_incomplete: bool = False
    # Alle biler vagten er kørt i: (start, slut, registreringsnummer) i dansk
    # lokal tid, kronologisk. Samme bil kan optræde flere gange (A -> B -> A).
    vehicle_uses: list[tuple[datetime, datetime, str]] = None


def parse_ddd_file(file_path: Path) -> list[ParsedActivity]:
    """Parse a .ddd driver card file and return activities per working day."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "rb") as f:
        data = f.read()

    card_number = _extract_card_number(data)
    vehicle_records = _extract_vehicle_usage_records(data)
    daily_odometer = _extract_daily_odometer(data)
    daily_records = _find_all_daily_records(data, vehicle_records)

    # Dags-records dateret EFTER udlæsningen kan ikke være ægte – de er
    # fejlfortolkede/korrupte poster (bekræftet 2026-10-02: Benny Hansen,
    # en post dateret 2/6-2034 i en udlæsning fra 28/9-2026). Ud over at blive
    # importeret som en meningsløs vagt, skubbede den udlæsningens reelle
    # sidste vagt væk fra pladsen som "sidste vagt i filen", så den delvise
    # vagt (05:58-10:01) ikke blev markeret ufuldstændig – og hver genimport
    # oprettede derfor en ny dublet-linje for dagen.
    read_date = _download_date(file_path)
    daily_records = [r for r in daily_records if r[0].date() <= read_date]

    if not daily_records:
        return []

    return _build_activities(
        card_number, vehicle_records, daily_odometer, daily_records, str(file_path),
        vehicle_uses=_extract_vehicle_uses(data),
    )


_DOWNLOAD_NAME_RE = re.compile(r"^C_(\d{8})_(\d{4})_")


def _download_date(file_path: Path):
    """UTC-datoen kortet blev udlæst, fra filnavnet (C_ÅÅÅÅMMDD_TTMM_...).
    Følger filnavnet ikke mønstret, bruges filens ændringstidspunkt – det kan
    aldrig ligge før udlæsningen, så det er en sikker øvre grænse."""
    m = _DOWNLOAD_NAME_RE.match(file_path.name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            pass
    return datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).date()


DEFAULT_MAX_FILE_AGE_DAYS = 7


def scan_ddd_folder(
    folder_path: Path,
    max_age_days: int | None = DEFAULT_MAX_FILE_AGE_DAYS,
    now: datetime | None = None,
) -> tuple[list[tuple[Path, list[ParsedActivity]]], list[str]]:
    """
    Scan folder (inkl. alle undermapper) for .ddd-filer.
    Filer med senest-ændret-tidspunkt ældre end `max_age_days` dage
    springes stille over – de er med stor sandsynlighed allerede importeret
    ved en tidligere scanning af mappen, og at genparse dem hver gang er
    unødigt arbejde. Sæt max_age_days=None for at scanne uden aldersgrænse
    (fx en manuel oprydning af en hel backlog).
    Returns (results, errors) – ikke-parsebare filer rapporteres som fejl i
    stedet for kun at blive printet til serverkonsollen.
    """
    results = []
    errors = []
    # set(): på filsystemer uden versalfølsomhed (Windows) matcher "*.ddd" og
    # "*.DDD" de samme filer, og ville ellers behandle hver fil to gange.
    ddd_files = sorted(
        set(folder_path.rglob("*.ddd")) | set(folder_path.rglob("*.DDD"))
    )
    if max_age_days is not None:
        cutoff = (now or datetime.now()) - timedelta(days=max_age_days)
        ddd_files = [f for f in ddd_files if datetime.fromtimestamp(f.stat().st_mtime) >= cutoff]
    for f in ddd_files:
        try:
            activities = parse_ddd_file(f)
            results.append((f, activities))
        except Exception as e:
            errors.append(f"{f.name}: fejl ved import ({e})")
    return results, errors


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_vehicle_usage_records(data: bytes) -> list[tuple[datetime, datetime, str]]:
    """
    Finder CardVehicleRecords: EU-tachografkortets tabel over hvilken bil der
    blev brugt i hvilket tidsrum. Fast 31-byte struktur pr. post:
      3 bytes  vehicleOdometerBegin
      3 bytes  vehicleOdometerEnd
      4 bytes  vehicleFirstUse   (TimeReal, UTC)
      4 bytes  vehicleLastUse    (TimeReal, UTC)
      1 byte   vehicleRegistrationNation
      1 byte   codePage
      13 bytes vehicleRegistrationNumber (ASCII, mellemrums-paddet)
      2 bytes  vuDataBlockCounter

    Et førerkort har IKKE nødvendigvis kun én bil for hele filen – chaufføren
    kan have kørt i flere forskellige biler over tid (bekræftet ved
    byte-analyse 2026-09-02: Anders Jersild Nielsens fil indeholdt bl.a.
    DR30578, DX22215, DH56162 og EE20981 i forskellige perioder). Denne
    funktion returnerer ALLE plausible (first_use, last_use, reg)-poster, så
    den rigtige bil kan slås op pr. vagt ud fra dens eget tidsrum – i stedet
    for (den tidligere fejlbehæftede tilgang) at antage ét globalt
    registreringsnummer for hele filen ud fra det først fundne heuristiske
    byte-mønster i filen, som lige så godt kunne stamme fra en helt anden,
    ikke-relateret blok tidligere i filen.

    En reel post dækker altid én enkelt køredag (first_use og last_use samme
    UTC-dato) – det filtrerer effektivt tilfældige byte-sekvenser fra, der
    godt kan ligne to gyldige tidsstempler, men som i praksis strækker sig
    over måneder/år (bekræftet: sådanne "poster" opstår systematisk ved
    fejlallignering, ofte forskudt præcis 31 byte fra en ægte post).
    """
    return [(first_dt, last_dt, reg) for _, first_dt, last_dt, reg in _scan_vehicle_records(data)]


def _scan_vehicle_records(data: bytes):
    """Fælles byte-scanning for CardVehicleRecords (se
    _extract_vehicle_usage_records): yielder (pos, first_use, last_use, reg)."""
    RECORD_SIZE = 31
    for pos in range(0, len(data) - RECORD_SIZE + 1):
        first_use = struct.unpack_from(">I", data, pos + 6)[0]
        if not (TS_MIN <= first_use <= TS_MAX):
            continue
        last_use = struct.unpack_from(">I", data, pos + 10)[0]
        if not (TS_MIN <= last_use <= TS_MAX) or last_use < first_use:
            continue
        first_dt = datetime.utcfromtimestamp(first_use)
        last_dt = datetime.utcfromtimestamp(last_use)
        if first_dt.date() != last_dt.date():
            continue
        reg_bytes = data[pos + 16: pos + 29]
        reg = reg_bytes.split(b"\x00")[0].decode("ascii", errors="ignore").strip()
        if not re.fullmatch(r'[A-Z0-9]{4,13}', reg):
            continue
        if not (re.search(r'[A-Z]', reg) and re.search(r'\d', reg)):
            continue
        yield pos, first_dt, last_dt, reg


_VIN_RE = re.compile(rb'[A-HJ-NPR-Z0-9]{17}')


def _extract_vehicle_uses(data: bytes) -> list[tuple[datetime, datetime, str]]:
    """
    Strengere udgave af _extract_vehicle_usage_records til listen over ALLE
    biler en vagt er kørt i (Activity.vehicle_uses). Hovedbilen
    (vehicle_registration) slås fortsat op via den gamle funktion, så
    vagtplan/timeseddel/CSV er uændrede.

    To ekstra filtre, bekræftet ved byte-analyse af de reelle filer 2026-09-30:
    - codePage-byten skal være gyldig (1-16). En forskudt læsning inde i en
      ægte post gav ellers et falsk "M23112" midt i DM23112's tidsrum
      (Eriksen 13-04-2026, codePage-byte = 0x44 'D').
    - Kortet har to tabeller: Gen1 (31-byte poster) og Gen2 (samme 31 byte
      efterfulgt af 17-tegns VIN). Gen2-tabellen skrives kun af Gen2-
      tachografer, så en tur i en ældre bil mangler dér, og bilen før/efter
      står som ét sammenhængende tidsrum (Nicolaisen 03-07-2026: DL52884
      04:55-12:19 i Gen2, mens Gen1 har DL52884 / CH78037 / DL52884). Gen1-
      posterne bruges derfor; en Gen2-post kun på datoer hvor Gen1 intet har
      (Gen2-tabellen rækker længere tilbage i tid).
    """
    gen1: set = set()
    gen2: set = set()
    for pos, first_dt, last_dt, reg in _scan_vehicle_records(data):
        if not (1 <= data[pos + 15] <= 16):
            continue
        target = gen2 if _VIN_RE.fullmatch(data[pos + 31: pos + 48]) else gen1
        target.add((first_dt, last_dt, reg))
    gen1_dates = {first_dt.date() for first_dt, _, _ in gen1}
    records = gen1 | {r for r in gen2 if r[0].date() not in gen1_dates}
    return sorted(records)


def _lookup_vehicle_registration(
    start_dt: datetime, end_dt: datetime, vehicle_records: list[tuple[datetime, datetime, str]],
) -> str | None:
    """Finder registreringsnummeret der dækker vagtens tidsrum bedst (størst overlap)."""
    best_reg = None
    best_overlap = 0.0
    for rec_start, rec_end, reg in vehicle_records:
        overlap_start = max(start_dt, rec_start)
        overlap_end = min(end_dt, rec_end)
        overlap = (overlap_end - overlap_start).total_seconds()
        if overlap > best_overlap:
            best_overlap = overlap
            best_reg = reg
    return best_reg


def _lookup_vehicle_uses(
    start_dt: datetime, end_dt: datetime, vehicle_uses: list[tuple[datetime, datetime, str]],
) -> list[tuple[datetime, datetime, str]]:
    """Alle bilposter (UTC) der overlapper vagtens tidsrum, klippet til vagten
    og sorteret kronologisk. Samme bil kan optræde flere gange (A -> B -> A).
    Bilposterne har sekunder; de afrundes ned til hele minutter som vagtens
    egne tider."""
    uses = []
    for rec_start, rec_end, reg in vehicle_uses:
        rec_start = rec_start.replace(second=0, microsecond=0)
        rec_end = rec_end.replace(second=0, microsecond=0)
        s, e = max(start_dt, rec_start), min(end_dt, rec_end)
        if e > s:
            uses.append((s, e, reg))
    return sorted(uses)


def _extract_card_number(data: bytes) -> str:
    """
    Find the tachograph card number in the file.

    Kortnummerfeltet (CardNumber) er ifølge EU-tachografspecifikationen 16 tegn:
    14 tegn driverIdentification + 1 ciffer udskiftningsindeks + 1 ciffer
    fornyelsesindeks. De sidste 2 cifre hører ikke til det stabile kortnummer
    (de ændrer sig når kortet fornys/udskiftes), så vi returnerer kun de
    første 14 tegn.

    Kortnummeret læses fra identifikationsblokken (EF Identification, tag
    05 20, datatype 00/02, længde 143 = 0x008F): 1 byte udstedende land
    efterfulgt af de 16 tegn. Det virker også for udenlandske kort, hvor
    nummeret indeholder bogstaver (fx tysk DF0000518081X0). Bekræftet
    2026-10-09 på de danske testfiler: giver samme nummer som det gamle
    mønster. Findes blokken ikke, bruges det gamle mønster (DK-format).
    """
    match = re.search(rb'\x05\x20[\x00\x02]\x00\x8f.([\x21-\x7e]{14})', data, re.S)
    if match:
        return match.group(1).decode("ascii")
    match = re.search(rb'[A-Z]{2}\d{14}', data)
    if match:
        return match.group(0)[:14].decode("ascii")
    return "UNKNOWN"


def _extract_daily_odometer(data: bytes) -> dict[int, int]:
    """
    Finder tabellen med km-standen ved starten af hver køretur/dag.

    Bekræftet ved byte-analyse (2026-07-02): filen indeholder et kompakt array
    af 20-byte elementer i kronologisk rækkefølge:
      3 bytes:  km-stand (big-endian)
      4 bytes:  tidsstempel (TimeReal, UTC) – matcher dagens beregnede
                dagsstart (day_start_minute) til minuttet
      13 bytes: øvrige data (bl.a. køretøjsregistrering ved køretøjsskift)

    Der er ingen pålidelig fast start-offset eller TLV-tag at søge efter, så
    tabellen findes ved kæde-validering: det længste sammenhængende forløb af
    plausible (km, tidsstempel)-par med præcis 20 bytes' afstand. Tilfældige
    byte-sekvenser andre steder i filen danner ikke kæder af denne længde.

    OBS: Førerkort gemmer kun et begrænset antal køretøjsbrug-poster, så
    tabellen dækker typisk ikke hele kortets historik – ældre dage vil derfor
    ikke have km-data.

    Returnerer {tidsstempel: km-stand}.
    """
    STRIDE = 20
    MIN_CHAIN_LENGTH = 5

    def read_pair(pos: int) -> tuple[int, int] | None:
        if pos < 0 or pos + 7 > len(data):
            return None
        odo = struct.unpack_from(">I", b"\x00" + data[pos:pos + 3])[0]
        if not (1 <= odo <= 2_000_000):
            return None
        ts = struct.unpack_from(">I", data, pos + 3)[0]
        if not (TS_MIN <= ts <= TS_MAX):
            return None
        return odo, ts

    visited: set[int] = set()
    best_chain: list[tuple[int, int]] = []
    for start in range(0, len(data) - 7):
        if start in visited:
            continue
        pair = read_pair(start)
        if pair is None:
            continue
        chain = [pair]
        pos = start + STRIDE
        while True:
            nxt = read_pair(pos)
            if nxt is None:
                break
            chain.append(nxt)
            visited.add(pos)
            pos += STRIDE
        if len(chain) >= MIN_CHAIN_LENGTH and len(chain) > len(best_chain):
            best_chain = chain

    return {ts: odo for odo, ts in best_chain}


def _lookup_daily_km(expected_ts: int, odometer_table: dict[int, int], tolerance_sec: int = 120) -> int | None:
    """Find km-standen tættest på det forventede tidsstempel (dagens beregnede start), inden for tolerance."""
    best = None
    best_diff = None
    for ts, odo in odometer_table.items():
        diff = abs(ts - expected_ts)
        if diff <= tolerance_sec and (best_diff is None or diff < best_diff):
            best = odo
            best_diff = diff
    return best


def _is_daily_chain_start(data: bytes, pos: int) -> bool:
    """
    Tjekker om `pos` er starten på mindst 2 sammenhængende gyldige dags-records.
    Heuristik: et record (min. 12 byte header) med gyldigt tidsstempel, hvor det
    næste record starter umiddelbart derefter, dets previousRecordLength matcher
    dette records length, og dets tidsstempel er inden for 7 dage af det første.
    """
    if pos + 28 > len(data):
        return False
    rec_len = struct.unpack_from(">H", data, pos + 2)[0]
    if rec_len < MIN_RECORD_SIZE or rec_len > 4096:
        return False
    if pos + rec_len + 4 > len(data):
        return False
    ts = struct.unpack_from(">I", data, pos + 4)[0]
    if not (TS_MIN <= ts <= TS_MAX):
        return False
    next_pos = pos + rec_len
    if next_pos + 4 > len(data):
        return False
    next_prev_len = struct.unpack_from(">H", data, next_pos)[0]
    next_rec_len  = struct.unpack_from(">H", data, next_pos + 2)[0]
    if next_prev_len != rec_len:
        return False
    if next_rec_len < MIN_RECORD_SIZE or next_rec_len > 4096:
        return False
    next_ts = struct.unpack_from(">I", data, next_pos + 4)[0]
    if not (TS_MIN <= next_ts <= TS_MAX):
        return False
    if abs(int(next_ts) - int(ts)) > 7 * 86400:
        return False
    return True


def _walk_daily_chain(data: bytes, start: int) -> list[tuple[datetime, int, bytes]]:
    """Walk consecutive daily records fra `start` til kæden brydes. Returns [(date, distance_km, activity_bytes), ...]."""
    records = []
    pos = start
    while pos + MIN_RECORD_SIZE <= len(data):
        rec_len = struct.unpack_from(">H", data, pos + 2)[0]
        if rec_len < MIN_RECORD_SIZE or rec_len > 4096:
            break
        if pos + rec_len > len(data):
            break
        ts       = struct.unpack_from(">I", data, pos + 4)[0]
        distance = struct.unpack_from(">H", data, pos + 10)[0]
        if not (TS_MIN <= ts <= TS_MAX):
            break

        # Activity bytes start at offset 12 within the record
        activity_bytes = data[pos + 12 : pos + rec_len]
        dt = datetime.utcfromtimestamp(ts)
        records.append((dt, distance, activity_bytes))
        pos += rec_len

    return records


def _last_activity_change_end_utc(day_dt: datetime, activity_bytes: bytes) -> datetime | None:
    """Tidspunktet (UTC, naiv) for dagsrecordets allersidste aktivitetsregistrering."""
    changes = _decode_activity_changes(activity_bytes)
    if not changes:
        return None
    return day_dt + timedelta(minutes=changes[-1][0])


def _lookup_last_vehicle_use_for_date(
    date, vehicle_records: list[tuple[datetime, datetime, str]],
) -> datetime | None:
    """Seneste `vehicleLastUse` blandt CardVehicleRecords der dækker denne dato."""
    matches = [last for first, last, _ in vehicle_records if first.date() == date]
    return max(matches) if matches else None


def _find_all_daily_records(
    data: bytes, vehicle_records: list[tuple[datetime, datetime, str]] | None = None,
) -> list[tuple[datetime, int, bytes]]:
    """
    Find ALLE dags-records i filen, ikke kun den første sammenhængende kæde.

    Tachograf-kort gemmer aktivitetsdata i en cirkulær buffer, og .ddd-filer kan
    indeholde flere separate og/eller duplikerede blokke med dags-records – ikke
    nødvendigvis i kronologisk byte-rækkefølge (bekræftet ved byte-analyse
    2026-07-26: samme fils data for en periode lå adskilt fra data for en
    efterfølgende periode, med en helt anden byteposition). En enkelt lineær
    scanning fra byte 0 (den tidligere `_find_daily_records_start`) kan derfor
    lande på en kort, ufuldstændig kæde og stoppe alt for tidligt, selvom resten
    af dagene findes andetsteds i filen.

    Denne funktion scanner hele filen for samtlige gyldige kæde-startpunkter,
    vandrer hver kæde, og fletter resultaterne pr. dato. Ved konflikt (samme
    dato fundet i flere kæder) foretrækkes en post med tidsstempel præcis ved
    midnat (som en gyldig dags-record altid har per spec) frem for en der
    ikke er – bekræftet ved byte-analyse 2026-07-29: to overlappende kæder
    kan give samme dato med hhv. en gyldig midnatspost og en fejlfortolket
    post (forkert tidsstempel og urealistisk stor distance), og "flest
    aktivitetsbytes" alene kan fejlagtigt foretrække den forkerte.

    Er begge (eller ingen af dem) ved midnat, kan de to poster stadig være
    reelt forskellige (samme dato optræder i to forskellige kort-downloads i
    filen, og den ene kæde slutter netop denne dato – dvs. kortet blev
    formentlig udlæst midt i vagten ved dét download – mens den anden kæde
    fortsætter med flere efterfølgende dage og derfor stammer fra et senere,
    mere komplet download). Bekræftet ved byte-analyse 2026-09-04 (Jesper
    Frederiksen 24/8: én post viste kørsel uafbrudt til 21:24 UTC, en anden
    samme dato sluttede korrekt 14:10 UTC): CardVehicleRecords (en langt
    mere robust, fast-struktureret tabel, se `_extract_vehicle_usage_records`)
    viste køretøjets `vehicleLastUse` til 14:10:28 UTC – kun 28 sekunder fra
    den korte posts sluttidspunkt, mod 7¼ time fra den lange. Findes der en
    CardVehicleRecords-post for datoen, afgøres konflikten derfor ud fra
    hvilken kandidat der ligger tættest på dens `vehicleLastUse`. Er der
    ingen vehicleLastUse at sammenligne med (eller er de lige tætte),
    afgøres det stadig af flest bytes.

    En gyldig kæde starter typisk ved hvert record i kæden (ikke kun ved
    kædens første record), så uden optimering ville samme kæde blive
    genvandret fra hver position i den (O(kædelængde²)). Allerede besøgte
    record-startpositioner markeres derfor og springes over, så hele filen
    kun gennemgås én gang (O(filstørrelse)) – samme teknik som i
    `_extract_daily_odometer`.
    """
    vehicle_records = vehicle_records or []
    merged: dict = {}
    visited: set[int] = set()
    n = len(data)
    pos = 0
    while pos < n - 28:
        if pos not in visited and _is_daily_chain_start(data, pos):
            walk_pos = pos
            for dt, distance, activity_bytes in _walk_daily_chain(data, pos):
                visited.add(walk_pos)
                walk_pos += len(activity_bytes) + 12
                key = dt.date()
                existing = merged.get(key)
                if existing is None:
                    merged[key] = (dt, distance, activity_bytes)
                    continue
                new_is_midnight = dt.time() == time(0, 0, 0)
                existing_is_midnight = existing[0].time() == time(0, 0, 0)
                if new_is_midnight and not existing_is_midnight:
                    merged[key] = (dt, distance, activity_bytes)
                    continue
                if new_is_midnight != existing_is_midnight:
                    continue  # existing er allerede midnatsposten

                vehicle_last_use = _lookup_last_vehicle_use_for_date(key, vehicle_records)
                if vehicle_last_use is not None:
                    new_end = _last_activity_change_end_utc(dt, activity_bytes)
                    existing_end = _last_activity_change_end_utc(existing[0], existing[2])
                    if new_end is not None and existing_end is not None:
                        new_diff = abs((new_end - vehicle_last_use).total_seconds())
                        existing_diff = abs((existing_end - vehicle_last_use).total_seconds())
                        if new_diff != existing_diff:
                            if new_diff < existing_diff:
                                merged[key] = (dt, distance, activity_bytes)
                            continue

                if len(activity_bytes) > len(existing[2]):
                    merged[key] = (dt, distance, activity_bytes)
        pos += 1
    return [merged[k] for k in sorted(merged)]


def _decode_activity_changes(activity_bytes: bytes) -> list[tuple[int, int]]:
    """
    Decode 2-byte ActivityChangeInfo records.
    Returns sorted, deduplicated list of (minutes_from_midnight, activity) for
    driver slot only – dedupliceret på selve (minut, aktivitet)-parret, IKKE
    på cardPresent-bitten (som _decode_activity_changes_full bevarer). To rå
    ord med samme (minut, aktivitet) men forskellig cardPresent-bit (set i
    praksis, fx Finn Thor Eriksen 28/5 og Jesper Frederiksen 31/8) skal
    stadig kun give ÉT element her, som før denne bit blev tilføjet.
    """
    seen: set[tuple[int, int]] = set()
    result = []
    for m, a, _card in _decode_activity_changes_full(activity_bytes):
        if (m, a) not in seen:
            seen.add((m, a))
            result.append((m, a))
    return result


def _decode_activity_changes_full(activity_bytes: bytes) -> list[tuple[int, int, int]]:
    """
    Som _decode_activity_changes, men bevarer også bit 13 ("cardPresent" – 0
    når kortet er ISAT, 1 når det IKKE er isat, jf. spec). Bruges til at finde
    det præcise minut kortet blev sat i, uafhængigt af aktivitets-typen (se
    day_start_minute i _build_activities).
    """
    changes = []
    for i in range(0, len(activity_bytes) - 1, 2):
        word = struct.unpack_from(">H", activity_bytes, i)[0]
        slot         = (word >> 15) & 0x1
        card_present = (word >> 13) & 0x1
        activity     = (word >> 11) & 0x3   # bits 12-11
        minutes      = word & 0x7FF          # bits 10-0
        if slot != 0:
            continue
        if minutes > 1439:
            continue
        changes.append((minutes, activity, card_present))
    # Sort by time and deduplicate
    seen: set[tuple[int, int, int]] = set()
    result = []
    for m, a, c in sorted(changes):
        if (m, a, c) not in seen:
            seen.add((m, a, c))
            result.append((m, a, c))
    return result


ACTIVITY_NAMES = {
    ACTIVITY_REST: "rest",
    ACTIVITY_AVAILABILITY: "availability",
    ACTIVITY_WORK: "work",
    ACTIVITY_DRIVING: "driving",
}

# Skel mellem en pause i en vagt og skiftet mellem to vagter. EU-reglerne
# kræver mindst 9-11 timers daglig hviletid, mens pauser i en vagt normalt er
# under 1 time – 4 timer ligger trygt imellem. Bekræftet med bruger 2026-07-29
# ud fra konkrete sager (47 min = pause i vagten, ~10 timer = skel mellem vagter).
LONG_REST_THRESHOLD_MINUTES = 4 * 60

# En udlæsning taget lige da chaufføren startede dagen (kortet stukket i
# kortlæseren minutter inde i "hvil", før selve vagten er begyndt) fanges IKKE
# af reglen nedenfor, fordi den kræver at vagten IKKE slutter i hvil. Ingen
# rigtig vagt varer under VERY_SHORT_READING_MINUTES i alt – uanset om den
# slutter i hvil eller ej – så det er et selvstændigt, pålideligt signal om at
# resten af dagen mangler (bekræftet 2026-09-22: Claus Lindskov Schmidt 15-16/9
# – en 3-minutters "hvil"-udlæsning kl. 03:3x blev opfattet som en fuldgyldig,
# afsluttet vagt og skabte en ny dublet-linje ved hver eneste genimport, fordi
# den aldrig blev genkendt som ufuldstændig).
VERY_SHORT_READING_MINUTES = 15

# Øvre grænse for hvor lang en "grænse-pause" (se _split_on_long_rests) må
# være for at blive vist som en del af en tilstødende vagt i stedet for at
# indgå i den udeladte lange hvileperiode. Bekræftede eksempler spænder fra
# 1-11 minutter (chaufføren gør klar til at køre) til 61 minutter (Steen
# John Nielsen 19/7->20/7, slår over til hvil et stykke tid før kortet
# tages ud) – 90 minutter giver margin til den slags uden at risikere at
# vise en hel dags egen (uafhængige) hvileperiode som var det en kort pause.
MAX_LEADING_PAUSE_MINUTES = 90


def _split_on_long_rests(
    segments: list[tuple[datetime, datetime, int]],
) -> list[list[tuple[datetime, datetime, int]]]:
    """
    Splitter en global, sammenhængende segmentliste (kan strække sig over
    flere kalenderdage – se _build_activities) i separate vagter ved enhver
    sammenhængende hvile-køre på mindst LONG_REST_THRESHOLD_MINUTES.

    En hvile-køre kan bestå af flere rå segmenter, og den udelades som
    helhed (hullet mellem to vagter) – MEN har køren mere end ét segment,
    kan et kort segment i hver ende blive stående som del af den vagt, den
    grænser op til, i stedet for at indgå i det udeladte hul:
      - det ALLERFØRSTE segment i køren kan bevares som den AFSLUTTENDE
        vagts sidste (trailing) pause, hvis resten af køren stadig når
        tærsklen uden det (fx et enkelt minuts hvil, lige inden kortet
        tages ud, før den lange natlige hviletid for alvor begynder).
      - det ALLERSIDSTE segment i køren kan bevares som den PÅFØLGENDE
        vagts indledende pause (chaufførens faktiske "klar til vagt"
        tidspunkt), på samme vilkår.
    Er hele køren under tærsklen, er det blot en almindelig pause i vagten
    og forbliver en del af den samme vagt.
    """
    shifts: list[list[tuple[datetime, datetime, int]]] = []
    current: list[tuple[datetime, datetime, int]] = []
    i = 0
    n = len(segments)
    while i < n:
        if segments[i][2] != ACTIVITY_REST:
            current.append(segments[i])
            i += 1
            continue

        j = i
        while j < n and segments[j][2] == ACTIVITY_REST:
            j += 1
        run = segments[i:j]
        run_total = sum((s[1] - s[0]).total_seconds() / 60 for s in run)

        if run_total < LONG_REST_THRESHOLD_MINUTES:
            current.extend(run)
        else:
            # Bevar evt. et kort allerførste segment som den afsluttende vagts
            # trailing pause – kun hvis der overhovedet er en vagt at hænge det
            # på, og resten af køren stadig er en reel lang hvileperiode uden det.
            first_duration = (run[0][1] - run[0][0]).total_seconds() / 60
            peeled_first = 0
            if (
                current
                and len(run) > 1
                and first_duration <= MAX_LEADING_PAUSE_MINUTES
                and (run_total - first_duration) >= LONG_REST_THRESHOLD_MINUTES
            ):
                current.append(run[0])
                peeled_first = 1

            if current:
                shifts.append(current)

            tail = run[peeled_first:]
            tail_total = run_total - (first_duration if peeled_first else 0)
            last_duration = (tail[-1][1] - tail[-1][0]).total_seconds() / 60
            if (
                len(tail) > 1
                and last_duration <= MAX_LEADING_PAUSE_MINUTES
                and (tail_total - last_duration) >= LONG_REST_THRESHOLD_MINUTES
            ):
                current = [tail[-1]]
            else:
                current = []
        i = j
    if current:
        shifts.append(current)
    return shifts


def _build_activities(
    card_number: str,
    vehicle_records: list[tuple[datetime, datetime, str]] | None,
    daily_odometer: dict[int, int],
    daily_records: list[tuple[datetime, int, bytes]],
    source_file: str,
    vehicle_uses: list[tuple[datetime, datetime, str]] | None = None,
) -> list[ParsedActivity]:
    """
    Konverterer dags-records til ParsedActivity-objekter pr. VAGT, ikke pr.
    kalenderdag.

    For hver dag beregnes dagens egen reelle startpunkt (day_start_minute)
    med samme regel som hidtil: changes[0] er altid en videreført status ved
    minut 0 – enten en reel igangværende aktivitet (dagen fortsætter blot
    gårsdagens vagt) eller blot en "hvil"-markør, i så fald ekskluderes den
    (og en efterfølgende kort hvil-post lige inden arbejdet begynder regnes
    som chaufførens faktiske dagsstart).

    Om denne dags data skal SAMMENKÆDES med den foregående (åbne) vagt
    afgøres ikke af dagsskiftet i sig selv, men af hvor lang den samlede
    pause reelt er, fra forrige vagts sidste registrering til denne dags
    egen beregnede start – er den under LONG_REST_THRESHOLD_MINUTES,
    fortsætter det som én vagt (bygger bro over det mellemliggende hul).
    Ellers afsluttes den forrige vagt, og denne dag starter en ny.

    En allerede sammenkædet vagt (evt. flerdags) splittes desuden ved enhver
    sammenhængende hvileperiode på mindst LONG_REST_THRESHOLD_MINUTES MIDT i
    forløbet (_split_on_long_rests) – det fanger flere separate vagter samme
    kalenderdag, adskilt af en lang hvileperiode.
    """
    vehicle_records = vehicle_records or []
    distance_by_date: dict = {}
    final_shifts: list[list[tuple[datetime, datetime, int]]] = []
    pending: list[tuple[datetime, datetime, int]] = []
    # Aktiviteten ved den seneste dags allersidste registrering – IKKE
    # nødvendigvis samme som pending's sidste SEGMENT (som slutter lige FØR
    # denne registrering). Det er denne værdi, der gælder i hullet ind i
    # næste dag, da den sidste registrering ikke selv får et segment.
    prev_day_last_activity: int | None = None
    # Tidspunktet for samme registrering – bruges til at afgøre om en
    # videreført ikke-hvil-status ved næste dags minut 0 er en reel
    # fortsættelse eller bare en hængende status (se nedenfor).
    prev_real_end_dt: datetime | None = None

    def finalize_pending():
        nonlocal pending
        if pending:
            final_shifts.extend(_split_on_long_rests(pending))
        pending = []

    for day_dt, distance, activity_bytes in daily_records:
        distance_by_date[day_dt.date()] = distance

        if distance == 0 and len(activity_bytes) <= 2:
            finalize_pending()
            continue

        changes_full = _decode_activity_changes_full(activity_bytes)
        # Deduplicer på selve (minut, aktivitet)-parret, ikke på cardPresent-
        # bitten – to rå ord kan dele (minut, aktivitet) men have forskellig
        # cardPresent (se _decode_activity_changes), og skal stadig kun tælle
        # som ét element her (samme kontrakt som før cardPresent-bitten blev
        # tilføjet i changes_full).
        seen_ma: set[tuple[int, int]] = set()
        changes = []
        for m, a, _card in changes_full:
            if (m, a) not in seen_ma:
                seen_ma.add((m, a))
                changes.append((m, a))
        if not changes:
            finalize_pending()
            continue

        first_nonrest_minute = next(
            (m for m, a in changes if a != ACTIVITY_REST), None
        )
        if first_nonrest_minute is None:
            finalize_pending()
            continue

        if changes[0][1] != ACTIVITY_REST:
            # Normalt starter dagens record altid ved minut 0, men det er set
            # ikke at holde stik (fx et ufuldstændigt record) – brug den
            # faktiske første registrering, ikke en antaget minut 0.
            day_start_minute = changes[0][0]
            # Minut 0 er en videreført status fra dagen inden – er der gået
            # mindst LONG_REST_THRESHOLD_MINUTES siden forrige dags sidste
            # rigtige registrering uden at noget er logget i mellemtiden, er
            # den videreførte ikke-hvil-status højst sandsynligt bare
            # "hængende" (chaufføren fik ikke skiftet kortet til hvil), ikke
            # en reel igangværende aktivitet. Spring den over ligesom en
            # indledende hvil-markør, og lad vagten starte ved den næste
            # rigtige registrering i stedet (bekræftet 2026-08-10: Peter
            # Mike Rasmussen 28/7 – "arbejde" stod uændret fra minut 0 kl.
            # 02 lokal til kl. 05:07, over 8 timer efter forrige vagts
            # afslutning kl. 17:39 den 27/7, hvorefter den rigtige vagt
            # startede).
            if (
                changes[0][0] == 0
                and len(changes) > 1
                and prev_real_end_dt is not None
                and (day_dt - prev_real_end_dt).total_seconds() / 60 >= LONG_REST_THRESHOLD_MINUTES
            ):
                day_start_minute = changes[1][0]
        else:
            if changes[0][0] != 0:
                # Dagens allerførste registrering ER selve denne hvilepost –
                # der er intet forud for den (dagens data starter simpelthen
                # her, ikke ved midnat), så den kan ikke være en "videreført"
                # status fra i går. Den udgør derfor chaufførens faktiske
                # dagsstart, uanset hvor kort den er (bekræftet 2026-09-03:
                # Mikkel Hørlin 2/9 – kortet fik status "hvil" kl. 06:54,
                # skiftede til "kørsel" kl. 07:02; vagten skal starte 06:54).
                day_start_minute = changes[0][0]
            else:
                # Minut 0 er en videreført hvil-status fra dagen inden – det
                # er som udgangspunkt ikke muligt at skelne fra rå data alene
                # om det er en ægte kort hvil eller bare "hængende"
                # midnatsstatus, så vi springer den over og lader vagten
                # starte ved næste rigtige (ikke-hvil) registrering.
                #
                # UNDTAGELSE: skifter "cardPresent"-bitten undervejs i denne
                # indledende hvileperiode fra "IKKE isat" til "isat" (kortet
                # SÆTTES I, uafhængigt af at aktiviteten stadig viser "hvil"
                # et par minutter endnu), er DET tidspunktet chaufførens dag
                # reelt begynder – ikke det senere tidspunkt hvor aktiviteten
                # skifter væk fra "hvil". Bekræftet 2026-09-04: Finn Thor
                # Eriksen 31/8 og 1/9 – minut 0 videreførte "intet kort isat,
                # crew" fra i går, kortet blev sat i 2 minutter FØR den næste
                # aktivitetsregistrering (som stadig var "hvil"), og
                # CardVehicleRecords' vehicleFirstUse (den uafhængige, langt
                # mere pålidelige køretøjsbrug-tabel) bekræftede present til
                # minuttet.
                #
                # Retningen er afgørende – kun 1 ("ikke isat") -> 0 ("isat")
                # er en indsættelse. Et skift den anden vej (0 -> 1, kortet
                # TAGES UD midt i den indledende hvileperiode) er IKKE
                # dagsstart, og skal fortsat falde tilbage til
                # first_nonrest_minute (bekræftet 2026-09-04: Anders Jersild
                # Nielsen 1/6 – kortet var isat videreført fra i går, blev
                # taget ud kl. minut 514, sat i igen inden kørsel begyndte
                # minut 589 – uden retningstjek ville minut 514 (udtagningen)
                # fejlagtigt være blevet brugt som dagsstart).
                card_insert_minute = None
                if changes_full[0][2] == 1:  # 1 = intet kort isat ved minut 0
                    card_insert_minute = next(
                        (m for m, a, c in changes_full[1:] if c == 0), None,
                    )
                if card_insert_minute is not None and card_insert_minute <= first_nonrest_minute:
                    day_start_minute = card_insert_minute
                else:
                    day_start_minute = first_nonrest_minute

        last_minute = changes[-1][0]
        if last_minute <= day_start_minute:
            finalize_pending()
            continue

        day_segments: list[tuple[datetime, datetime, int]] = []
        for i, (minute, activity) in enumerate(changes):
            if minute < day_start_minute:
                continue
            next_minute = changes[i + 1][0] if i + 1 < len(changes) else last_minute
            seg_start = max(minute, day_start_minute)
            seg_end = min(next_minute, last_minute)
            duration = max(0, seg_end - seg_start)
            if duration > 0:
                day_segments.append((
                    day_dt + timedelta(minutes=seg_start),
                    day_dt + timedelta(minutes=seg_end),
                    activity,
                ))
        if not day_segments:
            finalize_pending()
            continue

        day_own_start_dt = day_dt + timedelta(minutes=day_start_minute)
        if pending:
            gap_minutes = (day_own_start_dt - pending[-1][1]).total_seconds() / 60
            if gap_minutes < LONG_REST_THRESHOLD_MINUTES:
                if day_own_start_dt > pending[-1][1]:
                    # Bro over hullet mellem forrige dags allersidste registrering
                    # og denne dags egen start. Den sidste registrering i en dag
                    # får aldrig sit eget segment (den er kun et slutmærke), så
                    # dens aktivitet skal hentes fra prev_day_last_activity – IKKE
                    # fra pending's sidste SEGMENT, som gælder tiden FØR den
                    # sidste registrering, ikke tilstanden efter den.
                    pending.append((pending[-1][1], day_own_start_dt, prev_day_last_activity))
                pending.extend(day_segments)
            else:
                finalize_pending()
                pending = day_segments
        else:
            pending = day_segments

        prev_day_last_activity = changes[-1][1]
        prev_real_end_dt = day_dt + timedelta(minutes=last_minute)

    finalize_pending()

    last_file_date = max(distance_by_date) if distance_by_date else None

    # ── Trin 3: km_end kan kun beregnes ud fra en dags samlede distance, hvis
    # vagten dækker præcis én kalenderdag, OG ingen anden vagt også rører den
    # dag – ellers kan distancen ikke entydigt tilskrives denne ene vagt.
    dates_touched_per_shift = [
        {seg_start.date() for seg_start, seg_end, _ in shift} | {seg_end.date() for seg_start, seg_end, _ in shift}
        for shift in final_shifts
    ]
    date_shift_counts: dict = {}
    for dates in dates_touched_per_shift:
        for d in dates:
            date_shift_counts[d] = date_shift_counts.get(d, 0) + 1

    activities = []
    for shift_idx, shift in enumerate(final_shifts):
        start_dt = shift[0][0]
        end_dt = shift[-1][1]
        total_minutes = (end_dt - start_dt).total_seconds() / 60
        if total_minutes <= 0:
            continue

        mins = {ACTIVITY_REST: 0.0, ACTIVITY_AVAILABILITY: 0.0, ACTIVITY_WORK: 0.0, ACTIVITY_DRIVING: 0.0}
        pause_intervals: list[tuple[datetime, datetime]] = []
        segments: list[tuple[datetime, datetime, str]] = []
        for seg_start, seg_end, activity in shift:
            duration = (seg_end - seg_start).total_seconds() / 60
            mins[activity] = mins.get(activity, 0) + duration
            seg = (_utc_to_local(seg_start), _utc_to_local(seg_end))
            segments.append((seg[0], seg[1], ACTIVITY_NAMES.get(activity, "work")))
            if activity == ACTIVITY_REST:
                pause_intervals.append(seg)

        def pct(m: float) -> Decimal | None:
            return Decimal(str(round(m / total_minutes * 100, 2))) if total_minutes else None

        # Bekræftet på flere reelle filer (2026-07): når kortet udlæses midt i
        # en vagt, er dagens km-distance ofte endnu ikke skrevet (0), og vagten
        # slutter ikke i hvil – begge tegn samtidig er et pålideligt signal om
        # at resten mangler i filen. Gælder kun den allersidste vagt i filen.
        #
        # Km-distancen kan dog IKKE altid bruges alene: nogle kort skriver den
        # løbende gennem dagen i stedet for kun ved dagens afslutning, så en
        # udlæsning midt i vagten kan allerede vise et ikke-nul km-tal
        # (bekræftet 2026-08-10: Anders Jersild Nielsen 31/7 – kortet viste
        # 114 km ved en udlæsning kl. ca. 06, selvom vagten fortsatte til
        # 15:06). Derfor accepteres varigheden hidtil som et alternativt
        # signal: er den registrerede vagt markant kortere end
        # LONG_REST_THRESHOLD_MINUTES (samme grænse som skelner en pause i
        # vagten fra et skel mellem vagter et andet sted i filen), er det
        # usandsynligt at være en hel vagt, uanset km-tallet.
        last_date = end_dt.date()
        is_last_shift_in_file = (shift_idx == len(final_shifts) - 1) and last_date == last_file_date
        is_likely_incomplete = is_last_shift_in_file and (
            (
                shift[-1][2] != ACTIVITY_REST
                and (
                    distance_by_date.get(last_date, 0) == 0
                    or total_minutes < LONG_REST_THRESHOLD_MINUTES
                )
            )
            or total_minutes < VERY_SHORT_READING_MINUTES
        )

        day_start_ts = int(start_dt.replace(tzinfo=timezone.utc).timestamp())
        km_start = _lookup_daily_km(day_start_ts, daily_odometer)
        vehicle_registration = _lookup_vehicle_registration(start_dt, end_dt, vehicle_records)
        shift_vehicle_uses = [
            (_utc_to_local(s), _utc_to_local(e), reg)
            for s, e, reg in _lookup_vehicle_uses(start_dt, end_dt, vehicle_uses or [])
        ]
        dates_touched = dates_touched_per_shift[shift_idx]
        km_end = None
        if km_start is not None and len(dates_touched) == 1:
            only_date = next(iter(dates_touched))
            if date_shift_counts.get(only_date) == 1:
                distance = distance_by_date.get(only_date)
                if distance:
                    km_end = km_start + distance

        activities.append(
            ParsedActivity(
                tachograph_card_number=card_number,
                start_time=_utc_to_local(start_dt),
                end_time=_utc_to_local(end_dt),
                availability_time_pct=pct(mins[ACTIVITY_AVAILABILITY]),
                rest_pause_pct=pct(mins[ACTIVITY_REST]),
                other_work_pct=pct(mins[ACTIVITY_WORK]),
                driving_pct=pct(mins[ACTIVITY_DRIVING]),
                source_file=source_file,
                vehicle_registration=vehicle_registration,
                vehicle_uses=shift_vehicle_uses,
                km_start=km_start,
                km_end=km_end,
                pause_intervals=pause_intervals,
                segments=segments,
                is_likely_incomplete=is_likely_incomplete,
            )
        )

    return activities


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from pathlib import Path

    base = Path(__file__).resolve().parent.parent
    ddd_files = (
        list(base.glob("*.ddd"))
        + list(base.glob("*.DDD"))
        + list((base / "ddd_input").glob("*.ddd"))
        + list((base / "ddd_input").glob("*.DDD"))
    )

    if not ddd_files:
        print("Ingen .ddd filer fundet.")
    else:
        for f in ddd_files:
            print(f"\n{'='*65}")
            print(f"Fil: {f.name}")
            try:
                acts = parse_ddd_file(f)
                if acts:
                    print(f"Kortnummer : {acts[0].tachograph_card_number}")
                print(f"Arbejdsdage: {len(acts)}")
                for a in acts:
                    total_h = (a.end_time - a.start_time).seconds // 3600
                    total_m = ((a.end_time - a.start_time).seconds % 3600) // 60
                    print(
                        f"  {a.start_time.strftime('%Y-%m-%d %H:%M')} -> "
                        f"{a.end_time.strftime('%H:%M')}  "
                        f"({total_h}t{total_m:02d}m)  "
                        f"hvil={a.rest_pause_pct}%  "
                        f"rådigh={a.availability_time_pct}%  "
                        f"arb={a.other_work_pct}%  "
                        f"koersel={a.driving_pct}%"
                    )
            except Exception as e:
                import traceback
                print(f"FEJL: {e}")
                traceback.print_exc()
