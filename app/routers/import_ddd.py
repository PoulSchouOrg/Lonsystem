from datetime import datetime as _dt_now
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import require_permission, log_action
from calculators.auto_approval import should_auto_approve
from calculators.baseline_updater import update_baseline_from_activity
from database.session import get_db
from database.models import (
    AppUser, Employee, Activity, ActivitySource, ActivityStatus, PayPeriodStatus, Vehicle,
    DeclinedImport,
)
from calculators.pay_period import get_billing_period, get_or_create_period_for_date
from parsers.ddd_parser import scan_ddd_folder, ParsedActivity
from routers.activities import _recalculate_pcts

router = APIRouter(prefix="/api", tags=["import"])

DDD_INPUT_DIR = Path(__file__).resolve().parent.parent / "ddd_input"

_ddd_access = require_permission("import_ddd")


@router.post("/import-ddd")
def import_ddd_folder(allow_closed_period: bool = False,
                      current_user: AppUser = Depends(_ddd_access),
                      db: Session = Depends(get_db)):
    """
    Scan ddd_input/ folder and import all .ddd files.
    Skips activities that are already imported (same employee + start_time).
    """
    if not DDD_INPUT_DIR.exists():
        raise HTTPException(status_code=404, detail="ddd_input mappe ikke fundet")

    results, errors = scan_ddd_folder(DDD_INPUT_DIR)
    return _process_import_results(results, errors, current_user, db, allow_closed_period)


class DeclinedCandidate(BaseModel):
    employee_id: int
    start_time: str
    end_time: str


class DeclineClosedPeriodRequest(BaseModel):
    items: List[DeclinedCandidate]


@router.post("/decline-closed-period-import")
def decline_closed_period_import(
    body: DeclineClosedPeriodRequest,
    current_user: AppUser = Depends(_ddd_access),
    db: Session = Depends(get_db),
):
    """
    Husker at brugeren har valgt IKKE at importere disse vagter (lukket
    lønperiode) – de springes automatisk over uden ny bekræftelse ved
    fremtidige genimporter af samme fil(er).
    """
    added = 0
    # DB-sessionen bruger autoflush=False, så et tidligere db.add() i denne
    # samme request ikke er synligt for et efterfølgende db.query() – uden
    # dette lokale sæt ville den samme vagt optrædende to gange i body.items
    # (fx fundet i to forskellige .ddd-filer) blive tilføjet to gange og
    # ramme det unikke index (employee_id, start_time) ved commit, hvilket
    # fejlede HELE afvisningen (bekræftet 2026-08-11).
    seen: set[tuple[int, _dt_now]] = set()
    for item in body.items:
        start = _dt_now.fromisoformat(item.start_time)
        key = (item.employee_id, start)
        if key in seen:
            continue
        seen.add(key)
        exists = (
            db.query(DeclinedImport)
            .filter(DeclinedImport.employee_id == item.employee_id, DeclinedImport.start_time == start)
            .first()
        )
        if exists:
            continue
        db.add(DeclinedImport(
            employee_id=item.employee_id,
            start_time=start,
            end_time=_dt_now.fromisoformat(item.end_time),
            declined_by=current_user.initials,
        ))
        added += 1
    log_action(db, current_user, "decline_closed_period_import", "import", None,
               f"{added} vagt(er) markeret til altid at springes over (lukket lønperiode)")
    db.commit()
    return {"declined": added}


def _process_import_results(
    results: list, errors: list, current_user: AppUser, db: Session,
    allow_closed_period: bool = False,
) -> dict:
    """
    Importerer de fundne aktiviteter, sammentæller resultat pr. årsag og
    logger en hændelse i audit-loggen så alle skip-årsager kan læses bagefter.
    """
    imported = 0
    updated = 0
    skipped_unknown_card = 0
    skipped_duplicate = 0
    skipped_declined = 0
    skipped_conflict = 0
    conflicts: list[dict] = []
    unknown_cards: set[str] = set()
    zero_activity_files: list[str] = []
    # Samme vagt findes ofte i flere .ddd-filer (nye kortudlæsninger dækker
    # gerne de samme dage som en tidligere) – dedupliker pr. (medarbejder,
    # starttid), så brugeren ikke ser/afviser den samme vagt flere gange i
    # bekræftelses-popup'en (bekræftet 2026-08-11: dubletter fik "Nej,
    # spring over" til at fejle med en unik-indeks-fejl i afvisnings-tabellen).
    closed_period_candidates_by_key: dict[tuple[int, str], dict] = {}

    # Alle aktiviteter i én fil deler samme førerkortnummer – cache opslaget
    # pr. unikt kortnummer i stedet for at forespørge databasen for hver
    # eneste aktivitet (kan være 100+ pr. fil).
    employee_cache: dict[str, Employee | None] = {}

    for file_path, activities in results:
        if not activities:
            zero_activity_files.append(file_path.name)
        for act in activities:
            card = act.tachograph_card_number
            if card not in employee_cache:
                employee_cache[card] = (
                    db.query(Employee)
                    .filter(Employee.tachograph_card_number == card)
                    .first()
                )
            try:
                result, detail = _import_activity(
                    act, db, employee_cache[card], allow_closed_period
                )
            except Exception as e:
                # Uventet fejl (ikke den kendte SAVEPOINT-håndterede
                # unik-indeks-konflikt i _import_activity) – rul hele
                # sessionen tilbage, så den ikke efterlades i en "pending
                # rollback"-tilstand hvor ALLE efterfølgende aktiviteter i
                # denne kørsel ville fejle med en kryptisk følgefejl
                # (bekræftet 2026-09-04 ved genimport for Finn Thor Eriksen –
                # manglende rollback her lod én fejl vælte resten af
                # importen). Det koster de allerede flushede (men endnu ikke
                # committede) ændringer tidligere i denne kørsel, men det er
                # trygt: ingenting er committet til databasen endnu.
                db.rollback()
                errors.append(f"{file_path.name}: {e}")
                continue
            if result == "new":
                imported += 1
            elif result == "updated":
                updated += 1
            elif result == "skipped_unknown_card":
                skipped_unknown_card += 1
                unknown_cards.add(act.tachograph_card_number)
            elif result == "skipped_duplicate":
                skipped_duplicate += 1
            elif result == "skipped_declined":
                skipped_declined += 1
            elif result == "skipped_conflict":
                skipped_conflict += 1
                if detail:
                    conflicts.append(detail)
            elif result == "pending_closed_period":
                key = (detail["employee_id"], detail["start_time"])
                existing_candidate = closed_period_candidates_by_key.get(key)
                if existing_candidate is None or detail["end_time"] > existing_candidate["end_time"]:
                    closed_period_candidates_by_key[key] = detail

    closed_period_candidates = list(closed_period_candidates_by_key.values())
    skipped = skipped_unknown_card + skipped_duplicate + skipped_declined + skipped_conflict

    summary_parts = [
        f"{len(results)} fil(er) behandlet",
        f"{imported} importeret",
        f"{updated} opdateret",
    ]
    if skipped_unknown_card:
        summary_parts.append(
            f"{skipped_unknown_card} sprunget over (ukendt førerkortnummer: "
            f"{', '.join(sorted(unknown_cards))})"
        )
    if skipped_duplicate:
        summary_parts.append(f"{skipped_duplicate} sprunget over (allerede importeret)")
    if skipped_declined:
        summary_parts.append(f"{skipped_declined} sprunget over (tidligere afvist – lukket periode)")
    if skipped_conflict:
        summary_parts.append(
            f"{skipped_conflict} kunne IKKE rettes (kolliderer med en anden, allerede gemt "
            f"aktivitet for samme medarbejder på samme starttidspunkt – formentlig en ældre "
            f"duplikat-aktivitet der bør ryddes op manuelt)"
        )
    if closed_period_candidates:
        summary_parts.append(
            f"{len(closed_period_candidates)} vagt(er) afventer bekræftelse (lukket lønperiode)"
        )
    if zero_activity_files:
        summary_parts.append(
            f"{len(zero_activity_files)} fil(er) uden aktiviteter: "
            f"{', '.join(zero_activity_files)}"
        )
    if errors:
        summary_parts.append(f"{len(errors)} fejl: {'; '.join(errors)}")

    log_action(db, current_user, "ddd_import", "import", None, "; ".join(summary_parts))
    db.commit()

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "skipped_unknown_card": skipped_unknown_card,
        "skipped_duplicate": skipped_duplicate,
        "skipped_declined": skipped_declined,
        "skipped_conflict": skipped_conflict,
        "conflicts": conflicts,
        "unknown_cards": sorted(unknown_cards),
        "zero_activity_files": zero_activity_files,
        "errors": errors,
        "files_processed": len(results),
        "closed_period_candidates": closed_period_candidates,
    }


def _vehicle_uses_json(act) -> list | None:
    """ParsedActivity.vehicle_uses i Activity.vehicle_uses' JSON-format."""
    if not act.vehicle_uses:
        return None
    return [[s.isoformat(), e.isoformat(), reg] for s, e, reg in act.vehicle_uses]


def _baseline(a: Activity) -> tuple:
    """(start, slut, segments, pauser) som OPRINDELIGT importeret, før evt.
    manuel rettelse – det en genimport skal sammenlignes mod.

    Sammenlign mod det oprindeligt importerede, ikke mod de nuværende gemte
    værdier – ellers vil en genimport af uændret kildedata tolke en tidligere
    manuel tids-/pauserettelse som en afvigelse og lydløst overskrive den
    (bekræftet 2026-09-11: pause_intervals kan rettes manuelt via 'Ret
    linje'/'Tilpas', men blev hidtil ikke husket her). Samme princip for
    segments: en manuel pause->arbejde-rettelse ('Ret linje'/'Tilpas pause')
    ændrer a.segments, men skal ikke få en reimport af uændret kildedata til at
    ligne en afvigelse (bekræftet 2026-09-14: Alexander B. Knudsen og Claus
    Ulrik Nicolaisen 9/9)."""
    return (
        a.original_start_time or a.start_time,
        a.original_end_time or a.end_time,
        a.original_segments if a.original_segments is not None else (a.segments or []),
        a.original_pause_intervals if a.original_pause_intervals is not None else (a.pause_intervals or []),
    )


def _settled_line_covers(a: Activity, act: ParsedActivity,
                         new_segments: list, new_pause_intervals: list) -> bool:
    """Om en godkendt/deaktiveret linje allerede dækker udlæsningen fuldt, så
    en genimport ikke tilføjer noget nyt: enten identisk med det oprindeligt
    importerede, eller en forældet, ufuldstændig genlæsning af den.

    Ufuldstændig genlæsning (bekræftet 2026-09-18: Alexander B. Knudsen 11/9):
    scan_ddd_folder() genparser ALLE .ddd-filer under max_age_days ved hver
    import, også en ældre, delvis udlæsning fra midt i en vagt der senere er
    genindlæst fuldt og afgjort. Er den nye udlæsning markeret ufuldstændig,
    starter den samme sted, slutter tidligere, og er dens segmenter/pauser et
    rent præfiks af det allerede afgjorte, er der intet nyt at vise en bruger."""
    start, end, segments, pauses = _baseline(a)
    if (act.start_time == start and act.end_time == end
            and new_segments == segments and new_pause_intervals == pauses):
        return True
    return bool(
        act.is_likely_incomplete
        and act.start_time == start
        and act.end_time <= end
        and segments[: len(new_segments)] == new_segments
        and all(p in pauses for p in new_pause_intervals)
    )


def _import_activity(
    act: ParsedActivity, db: Session, employee: Employee | None,
    allow_closed_period: bool = False,
) -> tuple[str, dict | None]:
    """Import a single parsed activity. Returns (status, detail) where status is
    'new', 'updated', 'skipped_unknown_card', 'skipped_duplicate',
    'skipped_declined', 'skipped_conflict' or 'pending_closed_period' (detail
    is only set for 'skipped_conflict' and 'pending_closed_period')."""
    if not employee:
        return "skipped_unknown_card", None  # Unknown card number – employee must be created first

    # Brugeren har tidligere eksplicit valgt IKKE at importere denne vagt
    # (typisk: afvist en lukket-periode-bekræftelse) – husk det, så den ikke
    # bliver foreslået/importeret igen ved en senere genimport af filen.
    declined = (
        db.query(DeclinedImport)
        .filter(DeclinedImport.employee_id == employee.id, DeclinedImport.start_time == act.start_time)
        .first()
    )
    if declined:
        return "skipped_declined", None

    # Check for existing activity. Match på tidsoverlap i stedet for eksakt
    # start_time-lighed: en rettelse i parseren (eller en senere, mere
    # komplet kortudlæsning) kan ændre det beregnede starttidspunkt for en
    # vagt, og skal stadig kunne opdatere den eksisterende række i stedet for
    # fejlagtigt at oprette en duplikat (bekræftet 2026-09-03: Mikkel Hørlin
    # 2/9 – en parser-rettelse flyttede vagtens beregnede start fra 07:02 til
    # 06:54).
    #
    # Findes der BÅDE en godkendt/deaktiveret linje og en tidligere oprettet
    # pending-korrektionslinje for samme dag (fordi en genimport engang fandt
    # en reel afvigelse, se needs_new_line nedenfor), skal den pending linje
    # foretrækkes. Uden denne sortering finder et opslag uden order_by ofte
    # den gamle, "frosne" godkendte linje igen – som ALDRIG selv opdateres –
    # og genimporten opretter derfor en helt ny konkurrerende linje for HVER
    # eneste efterfølgende import, i det uendelige (bekræftet 2026-09-11:
    # 1.273 dublet-rækker på tværs af 38 medarbejdere stammede fra netop
    # dette). Med sorteringen konvergerer alle senere importer i stedet til
    # at opdatere den ene, allerede oprettede korrektionslinje.
    #
    # Sekundær sortering (kun afgørende mellem ellers ligestillede kandidater):
    # foretræk en linje hvis OPRINDELIGT importerede tider overlapper vagten,
    # frem for en linje der kun overlapper fordi dens tider er trukket ud
    # manuelt. Uden den matcher en genimport af en deaktiveret delvagt ofte den
    # udvidede, godkendte linje i stedet, og da dens oprindelige tider ikke
    # passer, oprettes en ny dublet-linje (bekræftet 2026-09-30: Mathias Hardon
    # 24/9 og 25/9 – to tachograf-linjer slået sammen ved at flytte start/slut
    # på den ene og deaktivere den anden).
    baseline_start_col = func.coalesce(Activity.original_start_time, Activity.start_time)
    baseline_end_col = func.coalesce(Activity.original_end_time, Activity.end_time)
    existing = (
        db.query(Activity)
        .filter(
            Activity.employee_id == employee.id,
            Activity.source == ActivitySource.tachograph,
            Activity.start_time < act.end_time,
            Activity.end_time > act.start_time,
        )
        .order_by(
            case(
                (and_(Activity.status == ActivityStatus.pending,
                      Activity.parent_activity_id.is_(None)), 0),
                else_=1,
            ),
            case(
                (and_(baseline_start_col < act.end_time,
                      baseline_end_col > act.start_time), 0),
                else_=1,
            ),
        )
        .first()
    )
    if existing:
        # HELE denne blok køres i én SAVEPOINT (nested transaktion), åbnet
        # FØR noget som helst røres på `existing` – ikke kun omkring det
        # afsluttende flush(). Begrundelse (bekræftet ved fejlsøgning
        # 2026-09-04): Session.begin_nested() tager selv en "snapshot" ved
        # åbning, hvilket automatisk flusher ALLEREDE beskidte (ændrede, men
        # endnu ikke flushede) attributter FØR selve SAVEPOINT'et sættes –
        # rammer DEN flush et unikt-indeks-brud, sker det uden for
        # SAVEPOINT'ets beskyttelse, og en efterfølgende
        # `except IntegrityError` fanger ganske vist selve fejlen, men
        # sessionens tilstand er alligevel ødelagt (en senere
        # attributtilgang på samme objekt fejler med PendingRollbackError).
        # Åbnes SAVEPOINT'et derimod FØR nogen mutation, er der intet
        # "beskidt" at flushe ved åbningen, og et efterfølgende flush-brud
        # INDENFOR blokken rulles korrekt tilbage af SAVEPOINT'et alene –
        # resten af batch-importens transaktion (andre allerede flushede,
        # gyldige aktiviteter) berøres ikke.
        needs_new_line = False
        try:
            with db.begin_nested():
                # Opdater km-data hvis parseren fandt værdier og aktiviteten mangler dem
                changed = False
                if act.km_start is not None and existing.km_start is None:
                    existing.km_start = act.km_start
                    changed = True
                if act.km_end is not None and existing.km_end is None:
                    existing.km_end = act.km_end
                    changed = True

                # Ret registreringsnummeret uafhængigt af tid/segment-ændringerne
                # nedenfor – en tidligere fejlbehæftet parser-version kunne gemme et
                # forkert registreringsnummer for en dag der ellers ikke ændrer sig
                # ved genimport, og genimporten skal stadig kunne korrigere det. Feltet
                # er metadata uden betydning for løn/godkendelse, så det rettes
                # uanset aktivitetens status.
                if act.vehicle_registration and act.vehicle_registration != existing.vehicle_registration:
                    existing.vehicle_registration = act.vehicle_registration
                    v = db.query(Vehicle).filter(Vehicle.registration_number == act.vehicle_registration).first()
                    existing.vehicle_number = v.vehicle_number if v else None
                    changed = True
                # Listen over alle biler vagten er kørt i følger samme princip:
                # metadata der rettes ved genimport uanset status (vagter
                # importeret før 2026-09-30 har ingen liste endnu).
                new_vehicle_uses = _vehicle_uses_json(act)
                if new_vehicle_uses and new_vehicle_uses != existing.vehicle_uses:
                    existing.vehicle_uses = new_vehicle_uses
                    changed = True

                new_segments = [
                    [s.isoformat(), e.isoformat(), name] for s, e, name in (act.segments or [])
                ]
                new_pause_intervals = [
                    [s.isoformat(), e.isoformat()] for s, e in (act.pause_intervals or [])
                ]

                # En aktivitet der stadig er 'pending' og ikke en del af et split (er
                # hverken selv splittet op, eller en af de to dele et split skabte)
                # er endnu ikke taget stilling til – trygt at synkronisere den FULDT
                # ind fra den nyeste parsing, i begge retninger. Det dækker bl.a. en
                # rettelse i parseren der afslører en kortere, korrekt vagt end den
                # tidligere gemte (bekræftet 2026-09-04: en .ddd-fil kan indeholde to
                # modstridende dags-records for samme dato, og en parser-rettelse kan
                # derfor gøre både start senere og slut tidligere – se
                # ddd_parser._find_all_daily_records).
                #
                # Er den NYE udlæsning selv markeret ufuldstændig (kortet læst midt i
                # vagten), må den ALDRIG lægges fuldt ind, uanset status – ellers vil
                # en ældre, ufuldstændig fil (importeret efter den komplette, fx pga.
                # mappenavne der sorteres alfabetisk og ikke efter udlæsningsdato)
                # kunne slette allerede kendte, korrekte pauser/segmenter (bekræftet
                # 2026-08-10: Alexander B. Knudsen 3/8).
                can_resync_fully = (
                    existing.status == ActivityStatus.pending
                    and existing.parent_activity_id is None
                    and not act.is_likely_incomplete
                )

                # Sammenlign mod det OPRINDELIGT importerede (se _baseline).
                baseline_start, baseline_end, baseline_segments, baseline_pauses = _baseline(existing)

                if can_resync_fully:
                    if (
                        act.start_time != baseline_start
                        or act.end_time != baseline_end
                        or new_segments != baseline_segments
                        or new_pause_intervals != baseline_pauses
                    ):
                        existing.start_time = act.start_time
                        existing.end_time = act.end_time
                        existing.segments = new_segments
                        existing.pause_intervals = new_pause_intervals
                        # Kildedata er reelt anderledes end det oprindeligt
                        # importerede – en evt. manuel rettelse er nu forældet
                        # og erstattet af den friske parsing, så der er intet
                        # tilbage at sammenligne fremtidige genimporter mod.
                        existing.original_start_time = None
                        existing.original_end_time = None
                        existing.original_pause_intervals = None
                        existing.original_segments = None
                        existing.availability_time_pct = act.availability_time_pct
                        existing.rest_pause_pct = act.rest_pause_pct
                        existing.other_work_pct = act.other_work_pct
                        existing.driving_pct = act.driving_pct
                        existing.is_likely_incomplete = act.is_likely_incomplete
                        changed = True
                elif existing.status == ActivityStatus.pending:
                    # Stadig pending, men enten en del af et split eller den nye
                    # udlæsning er ufuldstændig – tidsrummet er allerede bevidst
                    # omfordelt (split) eller for usikkert til fuld overskrivning
                    # (ufuldstændig fil), så kun UDVID, aldrig forkort eller
                    # overskriv segmenter.
                    if act.start_time < existing.start_time:
                        cutoff = existing.start_time
                        existing.segments = [
                            s for s in new_segments if _dt_now.fromisoformat(s[1]) <= cutoff
                        ] + (existing.segments or [])
                        existing.pause_intervals = [
                            p for p in new_pause_intervals if _dt_now.fromisoformat(p[1]) <= cutoff
                        ] + (existing.pause_intervals or [])
                        existing.start_time = act.start_time
                        _recalculate_pcts(existing)
                        changed = True

                    if act.end_time > existing.end_time:
                        cutoff = existing.end_time
                        existing.segments = (existing.segments or []) + [
                            s for s in new_segments if _dt_now.fromisoformat(s[0]) >= cutoff
                        ]
                        existing.pause_intervals = (existing.pause_intervals or []) + [
                            p for p in new_pause_intervals if _dt_now.fromisoformat(p[0]) >= cutoff
                        ]
                        existing.end_time = act.end_time
                        _recalculate_pcts(existing)
                        existing.is_likely_incomplete = act.is_likely_incomplete
                        changed = True
                else:
                    # Godkendt eller deaktiveret – allerede taget endelig stilling
                    # til, og må ALDRIG ændres, udvides eller genåbnes af en
                    # genimport (bekræftet 2026-09-07: en tidligere "udvid og
                    # genåbn"-regel her fortrød manuel oprydning, fordi den ikke
                    # kunne skelne "deaktiveret fordi forkert/duplikat" fra
                    # "deaktiveret af anden grund"). Repræsenterer den nye
                    # udlæsning en anden eller længere vagt end den, der allerede
                    # er godkendt/deaktiveret, oprettes i stedet en helt ny,
                    # separat linje for dagen (pending) med den fulde, opdaterede
                    # vagt – den eksisterende række røres ikke. Det unikke indeks
                    # (se models.py::Activity) omfatter kun 'pending'-rækker, så
                    # den nye linje kan uden problemer have samme starttidspunkt
                    # som den godkendte/deaktiverede aktivitet.
                    #
                    # Opslaget ovenfor vælger kun ÉN kandidat, og flere afgjorte
                    # linjer kan overlappe samme vagt ligeværdigt – typisk en
                    # deaktiveret delvis udlæsning fra midt i vagten ved siden af
                    # den godkendte, fulde vagt. Før der oprettes en ny linje,
                    # tjekkes derfor ALLE overlappende afgjorte linjer: dækker
                    # blot én af dem allerede udlæsningen, er der intet nyt
                    # (bekræftet 2026-10-01: Alexander B. Knudsen 28/9 – opslaget
                    # ramte den deaktiverede 05:43-05:45-linje, og en ny linje
                    # identisk med den godkendte 05:43-13:40 blev oprettet).
                    if not _settled_line_covers(existing, act, new_segments, new_pause_intervals):
                        others = (
                            db.query(Activity)
                            .filter(
                                Activity.employee_id == employee.id,
                                Activity.source == ActivitySource.tachograph,
                                Activity.status.in_([ActivityStatus.approved, ActivityStatus.deactivated]),
                                Activity.id != existing.id,
                                baseline_start_col < act.end_time,
                                baseline_end_col > act.start_time,
                            )
                            .order_by(Activity.id)
                            .all()
                        )
                        match = next(
                            (o for o in others
                             if _settled_line_covers(o, act, new_segments, new_pause_intervals)),
                            None,
                        )
                        if match is None:
                            needs_new_line = True
                        elif new_vehicle_uses and new_vehicle_uses != match.vehicle_uses:
                            match.vehicle_uses = new_vehicle_uses
                            changed = True

                if changed:
                    db.flush()  # gør ændringen synlig i denne transaktion; committes samlet til sidst
        except IntegrityError:
            # existing.id/employee_id er trygge at læse her – SAVEPOINT'et blev
            # åbnet FØR eksisterende blev rørt, så rollback-to-savepoint
            # gendanner objektet fuldt ud (ikke bare markerer det "expired"
            # midt i en ødelagt session).
            return "skipped_conflict", {
                "employee_id": existing.employee_id,
                "activity_id": existing.id,
                "start_time": act.start_time.isoformat(),
                "end_time": act.end_time.isoformat(),
            }

        if not needs_new_line:
            if changed:
                return "updated", None
            return "skipped_duplicate", None
        # needs_new_line: eksisterende (godkendt/deaktiveret) række er urørt –
        # fald igennem til oprettelse af en ny, separat aktivitet nedenfor.

    natural_period = get_or_create_period_for_date(act.start_time.date(), db)
    if natural_period.status == PayPeriodStatus.closed and not allow_closed_period:
        # Vagten hører til en allerede lukket lønperiode ("sen registrering") –
        # opret den IKKE endnu. Brugeren skal først bekræfte i en pop-up om
        # vagten skal importeres (og dermed rulles frem til næste åbne periode,
        # se get_billing_period) eller helt springes over.
        return "pending_closed_period", {
            "employee": f"{employee.first_name} {employee.last_name}",
            "employee_id": employee.id,
            "start_time": act.start_time.isoformat(),
            "end_time": act.end_time.isoformat(),
            "period_start": natural_period.start_date.isoformat(),
            "period_end": natural_period.end_date.isoformat(),
        }

    pay_period = get_billing_period(act.start_time.date(), db)

    vehicle_number = None
    if act.vehicle_registration:
        v = db.query(Vehicle).filter(Vehicle.registration_number == act.vehicle_registration).first()
        if v:
            vehicle_number = v.vehicle_number

    activity = Activity(
        employee_id=employee.id,
        pay_period_id=pay_period.id,
        source=ActivitySource.tachograph,
        start_time=act.start_time,
        end_time=act.end_time,
        availability_time_pct=act.availability_time_pct,
        rest_pause_pct=act.rest_pause_pct,
        other_work_pct=act.other_work_pct,
        driving_pct=act.driving_pct,
        vehicle_registration=act.vehicle_registration,
        vehicle_number=vehicle_number,
        vehicle_uses=_vehicle_uses_json(act),
        km_start=act.km_start,
        km_end=act.km_end,
        pause_intervals=[
            [s.isoformat(), e.isoformat()] for s, e in (act.pause_intervals or [])
        ],
        segments=[
            [s.isoformat(), e.isoformat(), name] for s, e, name in (act.segments or [])
        ],
        status=ActivityStatus.pending,
        is_likely_incomplete=act.is_likely_incomplete,
    )
    try:
        # Nested transaktion (SAVEPOINT): hvis en samtidig import allerede har
        # indsat samme vagt (race condition, se det unikke indeks på Activity),
        # fanger vi kun DENNE aktivitets konflikt her – uden det ville hele
        # importens batch-transaktion (mange andre allerede flushede, gyldige
        # aktiviteter) rulles tilbage sammen med den. db.flush() tildeler
        # activity.id uden en fuld transaktions-commit pr. aktivitet.
        with db.begin_nested():
            db.add(activity)
            db.flush()
    except IntegrityError:
        return "skipped_duplicate", None

    ok, flags = should_auto_approve(activity, db)
    if ok:
        activity.status = ActivityStatus.approved
        activity.auto_approved = True
        activity.auto_approval_flags = []
        activity.approved_by = "AUTO"
        activity.approved_at = _dt_now.utcnow()
        db.flush()
        update_baseline_from_activity(activity, db)
    else:
        activity.auto_approval_flags = flags
        db.flush()

    return "new", None
