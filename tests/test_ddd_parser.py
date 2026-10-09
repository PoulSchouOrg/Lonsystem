import struct
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime, timedelta, timezone

from parsers.ddd_parser import (
    _build_activities, _utc_to_local, ACTIVITY_REST, ACTIVITY_WORK, ACTIVITY_DRIVING,
    scan_ddd_folder, _extract_vehicle_usage_records, _lookup_vehicle_registration,
    _extract_card_number,
)


def _identification_block(nation: int, card16: bytes) -> bytes:
    """EF Identification: tag 05 20, datatype, længde 143, land + 16-tegns kortnummer."""
    body = bytes([nation]) + card16
    return b"\x05\x20\x00\x00\x8f" + body + b"\x00" * (143 - len(body))


def test_card_number_danish():
    data = b"\xff\x01" + _identification_block(0x0E, b"DK00000178901010")
    assert _extract_card_number(data) == "DK000001789010"


def test_card_number_german_with_letter():
    """Tyske kort kan have bogstaver i nummeret – det gamle DK-mønster fandt dem ikke."""
    data = b"\xff\x01" + _identification_block(0x0D, b"DF0000518081X000")
    assert _extract_card_number(data) == "DF0000518081X0"


def test_card_number_fallback_without_identification_block():
    assert _extract_card_number(b"xxDK00000178901010yy") == "DK000001789010"


def _pack(changes):
    """changes: list af (minut_fra_midnat, aktivitet) for driver-slot (slot=0)."""
    return b"".join(struct.pack(">H", (activity & 0x3) << 11 | (minute & 0x7FF))
                     for minute, activity in changes)


def _pack_full(changes):
    """Som _pack, men changes: list af (minut, aktivitet, cardPresent) –
    cardPresent er bit 13 (0=isat, 1=ikke isat, jf. spec)."""
    return b"".join(
        struct.pack(">H", (card & 0x1) << 13 | (activity & 0x3) << 11 | (minute & 0x7FF))
        for minute, activity, card in changes
    )


def test_short_mid_shift_readout_flagged_incomplete_even_with_nonzero_km():
    """
    Reproducerer Anders Jersild Nielsen 31/7: kortet udlæses midt i vagten
    (kun 1t23m data), men km-distancen for dagen er allerede skrevet (114),
    så det gamle "distance==0"-krav overså den. Skal stadig markeres
    sandsynligvis ufuldstændig ud fra den korte varighed.
    """
    day = datetime(2026, 7, 31)
    changes = [(0, ACTIVITY_REST), (274, ACTIVITY_WORK), (357, ACTIVITY_WORK)]
    daily_records = [(day, 114, _pack(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].is_likely_incomplete is True


def test_full_length_shift_ending_non_rest_not_flagged():
    """
    Modsat tilfælde: en vagt på ni timer, der (fordi chaufføren tog kortet
    ud lige efter arbejdet) heller ikke slutter i hvil, og hvor km allerede
    er skrevet – skal IKKE markeres ufuldstændig, da varigheden er en hel
    normal arbejdsdag.
    """
    day = datetime(2026, 7, 31)
    changes = [(0, ACTIVITY_REST), (274, ACTIVITY_WORK), (274 + 540, ACTIVITY_WORK)]
    daily_records = [(day, 320, _pack(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].is_likely_incomplete is False


def test_zero_distance_short_shift_still_flagged():
    """Den oprindelige, allerede bekræftede sag (km==0) skal stadig virke."""
    day = datetime(2026, 8, 3)
    changes = [(0, ACTIVITY_REST), (345, ACTIVITY_WORK), (485, ACTIVITY_DRIVING)]
    daily_records = [(day, 0, _pack(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].is_likely_incomplete is True


def test_full_shift_ending_in_rest_not_flagged():
    """En vagt der afsluttes normalt (ender i hvil) skal aldrig markeres
    ufuldstændig, uanset varighed eller km-distance."""
    day = datetime(2026, 7, 31)
    changes = [(0, ACTIVITY_REST), (274, ACTIVITY_WORK), (357, ACTIVITY_REST), (400, ACTIVITY_REST)]
    daily_records = [(day, 0, _pack(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].is_likely_incomplete is False


def test_stale_minute_zero_status_skipped_after_long_gap():
    """
    Reproducerer Peter Mike Rasmussen 28/7: forrige dags reelle vagt slutter
    kl. 17:40 (minut 1060). Næste dags record starter kl. 00:00 med en
    videreført "arbejde"-status, der ikke ændrer sig før kl. 05:00 (minut
    300) – over 8 timer efter forrige vagts afslutning. Den fastfrosne
    status skal springes over, og vagten skal starte ved den næste RIGTIGE
    registrering (05:00), ikke ved midnat.
    """
    day1 = datetime(2026, 7, 27)
    day1_changes = [(0, ACTIVITY_REST), (300, ACTIVITY_WORK), (1060, ACTIVITY_WORK)]
    day2 = day1 + timedelta(days=1)
    day2_changes = [(0, ACTIVITY_WORK), (300, ACTIVITY_WORK), (310, ACTIVITY_DRIVING), (700, ACTIVITY_WORK)]
    daily_records = [
        (day1, 200, _pack(day1_changes)),
        (day2, 200, _pack(day2_changes)),
    ]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    expected_start = _utc_to_local(day2 + timedelta(minutes=300))
    day2_shift = next(a for a in acts if a.start_time.date() == expected_start.date())
    assert day2_shift.start_time == expected_start


def test_minute_zero_status_kept_when_gap_since_prior_shift_is_short():
    """
    Modsat tilfælde: forrige dags reelle vagt slutter sent (kl. 23:20,
    minut 1400) – kun 40 minutter før næste dags minut 0. Her ligner den
    videreførte status en ægte fortsættelse af en vagt, der går over
    midnat, og skal IKKE springes over.
    """
    day1 = datetime(2026, 7, 27)
    day1_changes = [(0, ACTIVITY_REST), (300, ACTIVITY_WORK), (1400, ACTIVITY_WORK)]
    day2 = day1 + timedelta(days=1)
    day2_changes = [(0, ACTIVITY_WORK), (300, ACTIVITY_WORK), (310, ACTIVITY_DRIVING), (700, ACTIVITY_WORK)]
    daily_records = [
        (day1, 200, _pack(day1_changes)),
        (day2, 200, _pack(day2_changes)),
    ]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    # Vagten bygger bro over midnat, så det er ÉN sammenhængende aktivitet
    # der starter dagen før og slutter dagen efter, ikke en ny startende kl. 00:00.
    assert len(acts) == 1
    assert acts[0].start_time.date() == _utc_to_local(day1 + timedelta(minutes=300)).date()
    assert acts[0].end_time == _utc_to_local(day2 + timedelta(minutes=700))


def test_entire_day_becomes_ghost_when_only_stale_status_and_nothing_real():
    """
    Reproducerer Jesper Frederiksen 16/5: efter at den fastfrosne
    minut-0-status er sprunget over, er der INGEN reel aktivitet tilbage
    den dag (kortet blev aldrig rigtig brugt). Dagen skal forsvinde helt
    som selvstændig vagt, ikke krympe til en kort spøgelsesvagt.
    """
    day1 = datetime(2026, 7, 27)
    day1_changes = [(0, ACTIVITY_REST), (300, ACTIVITY_WORK), (1060, ACTIVITY_WORK)]
    day2 = day1 + timedelta(days=1)
    day2_changes = [(0, ACTIVITY_WORK), (300, ACTIVITY_WORK)]  # ingen reel aktivitet efter minut 300
    daily_records = [
        (day1, 200, _pack(day1_changes)),
        (day2, 0, _pack(day2_changes)),
    ]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert all(a.start_time.date() != day2.date() for a in acts)


def test_short_leading_rest_not_at_midnight_kept_as_shift_start():
    """
    Reproducerer Mikkel Hørlin 2/9-2026: dagens allerførste registrering
    (ikke minut 0, men minut 294 = 04:54 UTC / 06:54 lokal) er "hvil", og
    skifter til "kørsel" 8 minutter senere (minut 302). Da der intet er
    forud for denne registrering (ingen videreført status fra i går), er
    den korte indledende hvil chaufførens faktiske dagsstart og skal IKKE
    droppes til fordel for det første ikke-hvil-tidspunkt.
    """
    day = datetime(2026, 9, 2)
    changes = [(294, ACTIVITY_REST), (302, ACTIVITY_DRIVING), (600, ACTIVITY_WORK)]
    daily_records = [(day, 65, _pack(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].start_time == _utc_to_local(day + timedelta(minutes=294))


def test_card_inserted_during_leading_rest_anchors_day_start():
    """
    Reproducerer Finn Thor Eriksen 31/8 og 1/9-2026: minut 0 viderefører en
    hvil-status uden isat kort (cardPresent=1) fra i går. Kortet SÆTTES I
    (cardPresent skifter til 0) ved minut 262 – stadig registreret som
    "hvil" – og aktiviteten skifter først væk fra hvil to minutter senere
    (minut 264). Dagens reelle start er isætnings-tidspunktet (262), ikke
    det senere aktivitetsskift.
    """
    day = datetime(2026, 8, 31)
    changes = [
        (0, ACTIVITY_REST, 1),
        (262, ACTIVITY_REST, 0),
        (264, ACTIVITY_WORK, 0),
        (600, ACTIVITY_DRIVING, 0),
    ]
    daily_records = [(day, 150, _pack_full(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].start_time == _utc_to_local(day + timedelta(minutes=262))


def test_card_removed_during_leading_rest_does_not_anchor_day_start():
    """
    Reproducerer Anders Jersild Nielsen 1/6-2026: minut 0 viderefører en
    hvil-status MED isat kort (cardPresent=0, en reelt fortsat vagt/hvile
    fra i går). Kortet TAGES UD midt i den indledende hvileperiode
    (cardPresent skifter til 1 ved minut 514), og sættes i igen inden næste
    rigtige registrering (minut 589). Uden retningstjek (kun "isat" (1) ->
    "ikke isat" (0) tæller som en indsættelse, ikke omvendt) ville
    udtagnings-tidspunktet (514) fejlagtigt blive brugt som dagsstart –
    her skal den i stedet falde tilbage til første ikke-hvil-registrering.
    """
    day = datetime(2026, 6, 1)
    changes = [
        (0, ACTIVITY_REST, 0),
        (514, ACTIVITY_REST, 1),
        (589, ACTIVITY_DRIVING, 0),
        (700, ACTIVITY_WORK, 0),
    ]
    daily_records = [(day, 200, _pack_full(changes))]

    acts = _build_activities("X", None, {}, daily_records, "test.ddd")

    assert len(acts) == 1
    assert acts[0].start_time == _utc_to_local(day + timedelta(minutes=589))


def test_decode_activity_changes_dedupes_on_minute_and_activity_only():
    """
    To rå ord kan dele (minut, aktivitet) men have forskellig cardPresent-bit
    (set i praksis, fx Finn Thor Eriksen 28/5 og Jesper Frederiksen 31/8) –
    _decode_activity_changes skal stadig kun returnere ÉT element for et
    sådant par, ligesom før cardPresent-bitten blev tilføjet.
    """
    from parsers.ddd_parser import _decode_activity_changes

    raw = _pack_full([
        (0, ACTIVITY_REST, 0),
        (300, ACTIVITY_WORK, 0),
        (300, ACTIVITY_WORK, 1),  # samme (minut, aktivitet), anden cardPresent
        (400, ACTIVITY_DRIVING, 0),
    ])

    result = _decode_activity_changes(raw)

    assert result == [(0, ACTIVITY_REST), (300, ACTIVITY_WORK), (400, ACTIVITY_DRIVING)]


def test_scan_ddd_folder_excludes_files_older_than_max_age(tmp_path):
    """
    scan_ddd_folder() gennemsøges hver gang hele mappen scannes (både ved
    ad hoc mappe-import og den faste ddd_input-scanning). Filer der allerede
    er flere dage gamle er med stor sandsynlighed allerede importeret ved en
    tidligere scanning - at genparse dem hver gang er unødigt arbejde. Filer
    ældre end max_age_days (default 7) springes derfor over.
    """
    now = datetime(2026, 8, 28, 12, 0)
    recent = tmp_path / "recent.ddd"
    recent.write_bytes(b"")
    old = tmp_path / "old.ddd"
    old.write_bytes(b"")
    recent_mtime = (now - timedelta(days=2)).timestamp()
    old_mtime = (now - timedelta(days=10)).timestamp()
    os.utime(recent, (recent_mtime, recent_mtime))
    os.utime(old, (old_mtime, old_mtime))

    results, errors = scan_ddd_folder(tmp_path, max_age_days=7, now=now)

    seen_names = {p.name for p, _ in results} | {e.split(":")[0] for e in errors}
    assert "recent.ddd" in seen_names
    assert "old.ddd" not in seen_names


def test_scan_ddd_folder_max_age_none_disables_filter(tmp_path):
    """max_age_days=None skal bevare den gamle adfærd (ingen aldersgrænse) –
    fx til en manuel oprydningsscanning af en hel backlog."""
    now = datetime(2026, 8, 28, 12, 0)
    old = tmp_path / "old.ddd"
    old.write_bytes(b"")
    old_mtime = (now - timedelta(days=10)).timestamp()
    os.utime(old, (old_mtime, old_mtime))

    results, errors = scan_ddd_folder(tmp_path, max_age_days=None, now=now)

    seen_names = {p.name for p, _ in results} | {e.split(":")[0] for e in errors}
    assert "old.ddd" in seen_names


def _pack_vehicle_record(odo_begin, odo_end, first_use_dt, last_use_dt, reg, nation=0x0E, codepage=0x01):
    """Bygger en 31-byte CardVehicleRecord (se _extract_vehicle_usage_records)."""
    first_ts = int(first_use_dt.replace(tzinfo=timezone.utc).timestamp())
    last_ts = int(last_use_dt.replace(tzinfo=timezone.utc).timestamp())
    return (
        struct.pack(">I", odo_begin)[1:]
        + struct.pack(">I", odo_end)[1:]
        + struct.pack(">I", first_ts)
        + struct.pack(">I", last_ts)
        + bytes([nation, codepage])
        + reg.encode("ascii").ljust(13)
        + b"\x00\x00"
    )


def test_extract_vehicle_usage_records_finds_real_records_ignores_decoy():
    """
    Reproducerer fejlen fra Anders Jersild Nielsen og Mathias Soltau Hansen
    (1/9): en tidligere, ikke-relateret byte-sekvens tidligt i filen kan
    tilfældigt ligne "codePage-byte + pladenummer" uden at være en reel
    CardVehicleRecord. Den skal IKKE længere blive valgt – kun poster med den
    fulde, gyldige 31-byte rekordstruktur (og som dækker én enkelt dag) tæller.
    """
    decoy = b"\x01CS50909      "  # ligner det gamle heuristik-mønster, men er ikke en rigtig record
    rec1 = _pack_vehicle_record(
        100, 200, datetime(2026, 9, 1, 3, 20, 7), datetime(2026, 9, 1, 13, 45, 37), "EB23579",
    )
    rec2 = _pack_vehicle_record(
        200, 300, datetime(2026, 9, 2, 3, 0, 0), datetime(2026, 9, 2, 13, 0, 0), "CT15491",
    )
    data = b"\x00" * 50 + decoy + b"\x00" * 50 + rec1 + rec2

    records = _extract_vehicle_usage_records(data)

    regs = {reg for _, _, reg in records}
    assert "EB23579" in regs
    assert "CT15491" in regs
    assert "CS50909" not in regs


def test_lookup_vehicle_registration_picks_record_matching_shift_date():
    """Hver vagt skal have sit EGET registreringsnummer, ikke et globalt for hele filen."""
    records = [
        (datetime(2026, 9, 1, 3, 20), datetime(2026, 9, 1, 13, 45), "EB23579"),
        (datetime(2026, 9, 2, 3, 0), datetime(2026, 9, 2, 13, 0), "CT15491"),
    ]

    reg_sep1 = _lookup_vehicle_registration(
        datetime(2026, 9, 1, 4, 0), datetime(2026, 9, 1, 12, 0), records,
    )
    reg_sep2 = _lookup_vehicle_registration(
        datetime(2026, 9, 2, 4, 0), datetime(2026, 9, 2, 12, 0), records,
    )

    assert reg_sep1 == "EB23579"
    assert reg_sep2 == "CT15491"


def test_build_activities_assigns_per_day_vehicle_registration():
    """
    Integrationstest: to vagter samme fil skal have hver deres korrekte
    registreringsnummer, hentet fra CardVehicleRecords-tabellen ud fra vagtens
    eget tidsrum – IKKE ét globalt gæt for hele filen.
    """
    day1 = datetime(2026, 9, 1)
    day2 = datetime(2026, 9, 2)
    changes = [(0, ACTIVITY_REST), (274, ACTIVITY_WORK), (600, ACTIVITY_WORK)]
    daily_records = [
        (day1, 50, _pack(changes)),
        (day2, 50, _pack(changes)),
    ]
    vehicle_records = [
        (datetime(2026, 9, 1, 3, 0), datetime(2026, 9, 1, 12, 0), "EB23579"),
        (datetime(2026, 9, 2, 3, 0), datetime(2026, 9, 2, 12, 0), "CT15491"),
    ]

    acts = _build_activities("X", vehicle_records, {}, daily_records, "test.ddd")

    assert len(acts) == 2
    assert acts[0].vehicle_registration == "EB23579"
    assert acts[1].vehicle_registration == "CT15491"


def test_parse_ddd_file_drops_daily_records_dated_after_download(tmp_path, monkeypatch):
    """
    Reproducerer Benny Hansen 28/9: en korrupt dags-post dateret 2034 i en
    udlæsning fra 28/9-2026 kl. 08:18 UTC skubbede den reelle, delvise vagt
    væk fra pladsen som sidste vagt i filen, så den ikke blev markeret
    ufuldstændig. Poster dateret efter udlæsningsdatoen skal ignoreres.
    """
    import parsers.ddd_parser as p

    day = datetime(2026, 9, 28)
    bogus = datetime(2034, 6, 2)
    records = [
        (day, 0, _pack([(0, ACTIVITY_REST), (238, ACTIVITY_DRIVING), (480, ACTIVITY_WORK), (481, ACTIVITY_WORK)])),
        (bogus, 50, _pack([(0, ACTIVITY_REST), (60, ACTIVITY_DRIVING), (600, ACTIVITY_REST)])),
    ]
    monkeypatch.setattr(p, "_extract_card_number", lambda d: "DK000000644960")
    monkeypatch.setattr(p, "_extract_vehicle_usage_records", lambda d: [])
    monkeypatch.setattr(p, "_extract_daily_odometer", lambda d: {})
    monkeypatch.setattr(p, "_extract_vehicle_uses", lambda d: [])
    monkeypatch.setattr(p, "_find_all_daily_records", lambda d, v=None: records)

    f = tmp_path / "C_20260928_0818_Hansen_Benny_DK00000064496003.ddd"
    f.write_bytes(b"\x00")
    acts = p.parse_ddd_file(f)

    assert [a.start_time.date() for a in acts] == [day.date()]
    assert acts[0].is_likely_incomplete


def test_download_date_falls_back_to_mtime_for_unknown_filename(tmp_path):
    from parsers.ddd_parser import _download_date

    f = tmp_path / "kort.ddd"
    f.write_bytes(b"\x00")
    ts = datetime(2026, 9, 28, 12, tzinfo=timezone.utc).timestamp()
    os.utime(f, (ts, ts))
    assert _download_date(f) == datetime(2026, 9, 28).date()
