from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime, Numeric,
    ForeignKey, Text, Enum, JSON, Index, UniqueConstraint, text
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func
import enum
from datetime import date


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    admin = "admin"
    lonbogholder = "lonbogholder"
    disponent = "disponent"


class AgreementKind(str, enum.Enum):
    """Aftale: timelønnet med fast eller ikke fastlagt arbejdstid."""
    hourly_fixed = "hourly_fixed"          # Timelønnet, fast arbejdstid
    hourly_flexible = "hourly_flexible"    # Timelønnet, ikke fastlagt arbejdstid


class ActivitySource(str, enum.Enum):
    tachograph = "tachograph"
    manual = "manual"
    vagtplan = "vagtplan"


class ActivityType(str, enum.Enum):
    normal = "normal"
    ferie = "ferie"
    fri = "fri"
    afspadsering = "afspadsering"
    skole_kursus = "skole_kursus"


class ActivityStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    deactivated = "deactivated"


class PayPeriodStatus(str, enum.Enum):
    open = "open"
    preview = "preview"
    closed = "closed"


# Default timefordeling: ingen timer (skal udfyldes ved oprettelse)
def default_work_schedule():
    return {"even": [0, 0, 0, 0, 0, 0, 0], "odd": [0, 0, 0, 0, 0, 0, 0]}


class MasterPosition(Base):
    """Stilling – valgmuligheder til medarbejderens Stilling-felt (Stamdata → Stillinger)."""
    __tablename__ = "master_positions"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    employee_number = Column(String, unique=True, nullable=False)   # Lønnummer
    tachograph_card_number = Column(String, unique=True, nullable=True)  # Førerkortnummer
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    address = Column(String, nullable=True)
    postal_code = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    mobile = Column(String, nullable=True)
    initials = Column(String(10), nullable=True)  # matcher app_users.initials for "egen linje"-rettighed i Vagtplan
    # Nøgle fra master_agreement_kinds.key – ikke længere en hård enum-kolonne,
    # da nye Aftale-typer kan tilføjes via Stamdata (se AgreementKind for de to
    # systemnøgler, som overtidsberegningen fortsat kender).
    agreement_kind = Column(String(50), nullable=False, default="hourly_fixed")
    agreement_type = Column(String, nullable=False)  # Overenskomsttype fra Excel-arket
    fuldloennet = Column(Boolean, default=True, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    hire_date = Column(Date, nullable=False)
    termination_date = Column(Date, nullable=False, default=date(9999, 12, 31))
    # Timefordeling over 14 dage: {"even": [man..søn], "odd": [man..søn]} i timer
    work_schedule = Column(JSON, nullable=False, default=default_work_schedule)
    cvr_number = Column(String(20), nullable=True)          # Tilknyttet CVR-nummer (None = standard)
    anciennitet_dismissed_at = Column(DateTime, nullable=True)  # Tidspunkt for afvist anciennitetsadvarsel
    terminsdato = Column(Date, nullable=True)  # Seneste terminsdato angivet ved oprettelse af en barsel-aktivitet
    paragraf_56 = Column(Boolean, default=False, nullable=False)
    paragraf_56_start_date = Column(Date, nullable=True)
    paragraf_56_end_date = Column(Date, nullable=True)
    afloeser = Column(Boolean, default=False, nullable=False)
    ot_extra_alle_timer = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    activities = relationship("Activity", back_populates="employee")
    baselines = relationship("EmployeeBaseline", back_populates="employee")
    dispatcher_group_id = Column(Integer, ForeignKey("dispatcher_groups.id"), nullable=True)
    dispatcher_group = relationship("DispatcherGroup", back_populates="employees")
    fast_bil = Column(Boolean, default=False, nullable=False)
    fast_bil_vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    fast_bil_vehicle = relationship("Vehicle", foreign_keys=[fast_bil_vehicle_id], backref="fast_bil_employees")
    # "Vognnummer ved fravær" – default vognnummer når der oprettes fravær for medarbejderen
    absence_vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)
    absence_vehicle = relationship("Vehicle", foreign_keys=[absence_vehicle_id])
    # Medarbejderregister-udvidelse 2026-10-01 (se docs/superpowers/specs/2026-10-01-medarbejderregister.md)
    position_id = Column(Integer, ForeignKey("master_positions.id"), nullable=True)
    position = relationship("MasterPosition")
    seniority_date = Column(Date, nullable=True)      # Anciennitetsdato – kun til jubilæumsadvarsel
    cpr_number = Column(String(11), nullable=True)    # ddmmåå-xxxx – maskeres uden 'view_cpr'
    elev = Column(Boolean, default=False, nullable=False)
    elev_start_date = Column(Date, nullable=True)
    elev_end_date = Column(Date, nullable=True)
    personaleforening = Column(Boolean, default=True, nullable=False)
    natarbejde_tillaeg = Column(Boolean, default=False, nullable=False)  # kun til filtrering

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Paragraf56AlertDismissal(Base):
    __tablename__ = "paragraf_56_alert_dismissals"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=False)
    alert_type = Column(String(20), nullable=False)  # "upcoming" | "expired" | "birthday_40" | "jubilee_25" | "elev_ÅÅÅÅ-MM-DD"
    dismissed_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("employee_id", "user_id", "alert_type", name="uq_paragraf56_dismissal"),
    )


class PayPeriod(Base):
    __tablename__ = "pay_periods"

    id = Column(Integer, primary_key=True)
    start_date = Column(Date, nullable=False, unique=True)
    end_date = Column(Date, nullable=False)
    status = Column(Enum(PayPeriodStatus), default=PayPeriodStatus.open, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(String, nullable=True)

    activities = relationship("Activity", back_populates="pay_period")
    payroll_runs = relationship("PayrollRun", back_populates="pay_period")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), nullable=False)
    trip_number = Column(String(6), nullable=True)
    source = Column(Enum(ActivitySource), nullable=False)
    activity_type = Column(String(50), default="normal", nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    availability_time_pct = Column(Numeric(5, 2), nullable=True)
    rest_pause_pct = Column(Numeric(5, 2), nullable=True)
    other_work_pct = Column(Numeric(5, 2), nullable=True)
    driving_pct = Column(Numeric(5, 2), nullable=True)
    loading_minutes = Column(Integer, nullable=True)
    unloading_minutes = Column(Integer, nullable=True)
    # Pauseintervaller [["ISO-start","ISO-slut"], ...] – pauser fratrækkes
    # i det tidsrum de afholdes (vigtigt for korrekt tillægsberegning)
    pause_intervals = Column(JSON, nullable=False, default=list)
    # Alle hændelsessegmenter fra tachografen:
    # [["ISO-start","ISO-slut","rest|availability|work|driving"], ...]
    segments = Column(JSON, nullable=False, default=list)
    created_by = Column(String, nullable=True)   # initialer på bruger der oprettede manuelt
    # Originale tider/pauser gemmes ved første manuelle rettelse (muliggør fortryd,
    # og lader en ddd-genimport sammenligne mod det oprindeligt importerede i
    # stedet for en senere manuel rettelse – ellers vil genimport af uændret
    # kildedata fejlagtigt tolke den manuelle rettelse som en afvigelse).
    original_start_time = Column(DateTime, nullable=True)
    original_end_time = Column(DateTime, nullable=True)
    original_pause_intervals = Column(JSON, nullable=True)
    original_segments = Column(JSON, nullable=True)
    status = Column(Enum(ActivityStatus), default=ActivityStatus.pending, nullable=False)
    approved_by = Column(String, nullable=True)     # initialer – sat ved godkendelse
    approved_at = Column(DateTime, nullable=True)
    deactivated_by = Column(String, nullable=True)  # initialer – sat ved deaktivering
    updated_by = Column(String, nullable=True)  # initialer – seneste bruger der ændrede aktiviteten
    comment = Column(Text, nullable=True)
    parent_activity_id = Column(Integer, ForeignKey("activities.id"), nullable=True)
    split_part = Column(Integer, nullable=True)
    vehicle_registration = Column(String, nullable=True)
    vehicle_number = Column(String, nullable=True)
    # Alle biler vagten er kørt i ifølge .ddd-filen: [[start_iso, slut_iso, reg], ...]
    # (lokal tid, kronologisk). vehicle_registration/vehicle_number er fortsat
    # hovedbilen (flest timer), som vagtplan/timeseddel/Danløn-CSV bruger;
    # Lønafregning deler vagten op pr. bil ud fra denne liste.
    vehicle_uses = Column(JSON, nullable=True)
    km_start = Column(Integer, nullable=True)
    km_end = Column(Integer, nullable=True)
    salt_supplement = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    auto_approved = Column(Boolean, default=False, nullable=False, server_default="0")
    auto_approval_flags = Column(JSON, nullable=False, default=list, server_default='[]')
    is_likely_incomplete = Column(Boolean, default=False, nullable=False, server_default="0")
    hidden_from_vagtplan = Column(Boolean, default=False, nullable=False, server_default="0")
    baseline_duration_minutes = Column(Numeric(10, 4), nullable=True)
    baseline_start_hour = Column(Numeric(8, 4), nullable=True)
    # Sættes KUN når en flerdags-fraværsperiode oprettes (samme værdi på alle
    # dagenes Activity-rækker) – bruges til at redigere periodens fra/til-dato
    # samlet. Null for enkeltdags-aktiviteter og for perioder oprettet før
    # denne kolonne fandtes (ingen tilbagevirkende migrering).
    absence_group_id = Column(String(36), nullable=True)

    employee = relationship("Employee", back_populates="activities")
    pay_period = relationship("PayPeriod", back_populates="activities")
    split_children = relationship("Activity", foreign_keys=[parent_activity_id])

    __table_args__ = (
        # Bruges af duplikat-tjek ved ddd-import (employee_id + start_time + source).
        # Uden dette index scanner SQLite hele tabellen for hver importeret aktivitet.
        Index("ix_activities_employee_start_source", "employee_id", "start_time", "source"),
        # (Det tidligere unikke indeks "uq_activities_employee_start_tachograph"
        # her er fjernet igen 2026-09-07: det eksisterede udelukkende for at
        # beskytte mod to SAMTIDIGE importer af samme vagt – men importen kører
        # kun for én medarbejder ad gangen, aldrig samtidig (heller ikke efter
        # den planlagte automatisering), så det scenarie kan reelt ikke opstå.
        # At en fuldstændig identisk vagt ikke importeres to gange sikres i
        # stedet fuldt ud af applikationslogikken i
        # import_ddd.py::_import_activity, som finder den eksisterende
        # aktivitet via tidsoverlap og kun opretter/ændrer noget hvis data
        # rent faktisk er anderledes.)
        # Lønkørsel, aktivitetsoversigt og fraværsoversigt filtrerer alle på
        # denne kombination (pay_period_id + status) – uden indekset bliver
        # det et fuldt tabel-scan for hver forespørgsel, efterhånden som
        # activities-tabellen vokser over måneder/år.
        Index("ix_activities_period_status", "pay_period_id", "status"),
        Index("ix_activities_absence_group", "absence_group_id"),
    )


class DispatcherGroup(Base):
    __tablename__ = "dispatcher_groups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    visible_in_activity_overview = Column(Boolean, nullable=False, default=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=True)

    employees = relationship("Employee", back_populates="dispatcher_group")
    # foreign_keys eksplicit angivet: Vehicle.dispatcher_group_id (tilføjet
    # senere, mange vogne -> én gruppe) forbinder de samme to tabeller med en
    # anden FK-kolonne end denne, hvilket ellers giver AmbiguousForeignKeysError.
    vehicle = relationship("Vehicle", foreign_keys=[vehicle_id])

    @property
    def vehicle_number(self) -> str | None:
        return self.vehicle.vehicle_number if self.vehicle else None


class VagtplanComment(Base):
    __tablename__ = "vagtplan_comments"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    date = Column(Date, nullable=False)
    text = Column(String(1000), nullable=False)
    created_by = Column(String(10), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    employee = relationship("Employee")

    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_vagtplan_comments_employee_date"),
    )


class DailyPlanAssignment(Base):
    __tablename__ = "daily_plan_assignments"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    task = Column(String, nullable=True)
    informed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    vehicle = relationship("Vehicle")
    employee = relationship("Employee")

    __table_args__ = (
        UniqueConstraint("date", "vehicle_id", name="uq_daily_plan_assignments_date_vehicle"),
    )


class DailyPlanExtraAssignment(Base):
    """De 10 faste 'EKSTRA'-rækker i Dagsplanen (hjælp på pladsen/lærlinge) -
    ikke knyttet til en rigtig Vehicle, kun et fast rækkenummer (slot 1-10)."""
    __tablename__ = "daily_plan_extra_assignments"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    slot = Column(Integer, nullable=False)  # 1-10
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    task = Column(String, nullable=True)
    informed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    employee = relationship("Employee")

    __table_args__ = (
        UniqueConstraint("date", "slot", name="uq_daily_plan_extra_assignments_date_slot"),
    )


class VehicleAbsence(Base):
    __tablename__ = "vehicle_absences"

    id = Column(Integer, primary_key=True)
    vehicle_id = Column(Integer, ForeignKey("vehicles.id"), nullable=False)
    date_from = Column(Date, nullable=False)
    date_to = Column(Date, nullable=True)  # null = étdags-fravær (samme dag som date_from)
    comment = Column(Text, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    vehicle = relationship("Vehicle")

    @property
    def vehicle_number(self) -> str | None:
        return self.vehicle.vehicle_number if self.vehicle else None


class PayrollRun(Base):
    __tablename__ = "payroll_runs"

    id = Column(Integer, primary_key=True)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), nullable=False)
    run_type = Column(String, nullable=False)  # "preview" or "final"
    run_at = Column(DateTime, server_default=func.now())
    run_by = Column(String, nullable=True)
    csv_path = Column(String, nullable=True)
    excel_path = Column(String, nullable=True)

    pay_period = relationship("PayPeriod", back_populates="payroll_runs")


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True)
    registration_number = Column(String, unique=True, nullable=False)  # Registreringsnummer (nummerplade)
    vehicle_number = Column(String, nullable=False)                     # Vognnummer
    description = Column(Text, nullable=True)                           # "Beskrivelse" (Dagsplan kol. 2)
    dispatcher_group_id = Column(Integer, ForeignKey("dispatcher_groups.id"), nullable=True)
    vognpark = Column(Boolean, default=False, nullable=False)           # Indgår i Dagsplanens vognkolonne
    created_at = Column(DateTime, server_default=func.now())

    # Mange vogne -> én gruppe. Adskilt fra DispatcherGroup.vehicle_id (én
    # gruppes "standardvogn", brugt til vognnummer-autoudfyldning ved
    # fraværstyper) - de to relationer løser hver sin opgave og skal derfor
    # begge have deres foreign_keys angivet eksplicit for at undgå
    # AmbiguousForeignKeysError (to FK-kolonner forbinder de samme to tabeller).
    dispatcher_group = relationship("DispatcherGroup", foreign_keys=[dispatcher_group_id])

    @property
    def dispatcher_group_name(self) -> str | None:
        return self.dispatcher_group.name if self.dispatcher_group else None

    @property
    def fast_bil_employee_name(self) -> str | None:
        """Navnet på den/de medarbejder(e) der har denne vogn som 'Fast bil'
        (jf. Employee.fast_bil_vehicle's backref). Normalt højst én, men
        intet forhindrer flere - vises da kommasepareret i stedet for at
        skjule en datainkonsistens."""
        if not self.fast_bil_employees:
            return None
        return ", ".join(e.name for e in self.fast_bil_employees)


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)          # fx "admin", "lonbogholder"
    display_name = Column(String, nullable=False)               # fx "Administrator"
    is_system = Column(Boolean, default=False, nullable=False)  # systemroller kan ikke slettes
    permissions = Column(JSON, nullable=False, default=list)    # ["payroll","import_ddd",...]


class AppUser(Base):
    __tablename__ = "app_users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    initials = Column(String(10), unique=True, nullable=False)
    email = Column(String, nullable=True)
    role = Column(String, nullable=False)   # navn på en rolle i roles-tabellen
    password_hash = Column(String, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    last_login = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, server_default=func.now())
    user_id = Column(Integer, ForeignKey("app_users.id"), nullable=True)
    user_initials = Column(String(10), nullable=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(Integer, nullable=True)
    details = Column(Text, nullable=True)

    __table_args__ = (
        # Brugeradmin-fanens hændelseslog sorterer på timestamp DESC med LIMIT
        # – uden indekset bliver det en fuld sortering af hele tabellen, som
        # vokser for hver brugerhandling i systemet, for evigt.
        Index("ix_audit_logs_timestamp", "timestamp"),
    )


class MasterAgreementType(Base):
    __tablename__ = "master_agreement_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, nullable=False)
    hourly_rate = Column(Numeric(10, 2), nullable=False)


class MasterAgreementKind(Base):
    __tablename__ = "master_agreement_kinds"

    id = Column(Integer, primary_key=True)
    key = Column(String(50), unique=True, nullable=False)
    label = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False)
    requires_agreement_type = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)


class MasterCvrNumber(Base):
    __tablename__ = "master_cvr_numbers"

    id = Column(Integer, primary_key=True)
    cvr_number = Column(String(20), unique=True, nullable=False)
    company_name = Column(String(200), nullable=False, default="")
    is_default = Column(Boolean, default=False, nullable=False)


class MasterOvertimeRate(Base):
    __tablename__ = "master_overtime_rates"

    id = Column(Integer, primary_key=True)
    label = Column(String(100), unique=True, nullable=False)
    rate = Column(Numeric(10, 4), nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False, server_default="0")


class MasterSupplementRate(Base):
    __tablename__ = "master_supplement_rates"

    id = Column(Integer, primary_key=True)
    label = Column(String(100), unique=True, nullable=False)
    rate = Column(Numeric(10, 4), nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False, server_default="0")


class MasterPayType(Base):
    __tablename__ = "master_pay_types"

    id = Column(Integer, primary_key=True)
    code_key = Column(String(50), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    danloen_code = Column(String(50), nullable=False, default="")
    include_in_csv = Column(Boolean, default=True, nullable=False)
    csv_quantity_type = Column(String(20), nullable=False, default="hours", server_default="hours")
    csv_rate_source = Column(String(30), nullable=False, default="hourly", server_default="hourly")
    csv_include_rate = Column(Boolean, default=True, nullable=False, server_default="1")
    csv_include_total = Column(Boolean, default=False, nullable=False, server_default="0")
    sort_order = Column(Integer, default=0, nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False, server_default="0")


class MasterAbsenceType(Base):
    __tablename__ = "master_absence_types"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=False)
    normalized_key = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_user_created = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)


class Holiday(Base):
    __tablename__ = "holidays"

    id                = Column(Integer, primary_key=True)
    date              = Column(Date, unique=True, nullable=False)
    name              = Column(String(200), nullable=False)
    half_day_from     = Column(String(5), nullable=True)    # "12:00" = fri fra middag; NULL = heldagshelligdag
    is_auto_generated = Column(Boolean, default=True, nullable=False)


class DeclinedImport(Base):
    """Vagte en bruger eksplicit har valgt IKKE at importere (fx en vagt i en
    allerede lukket lønperiode) – huskes så de ikke bliver foreslået igen ved
    en senere genimport af samme .ddd-fil."""
    __tablename__ = "declined_imports"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    declined_by = Column(String, nullable=True)
    declined_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_declined_imports_employee_start", "employee_id", "start_time", unique=True),
    )


class EmployeeBaseline(Base):
    __tablename__ = "employee_baselines"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    weekday = Column(Integer, nullable=False)          # 0=mandag … 6=søndag
    sample_count = Column(Integer, default=0, nullable=False)
    duration_mean_minutes = Column(Numeric(10, 4), default=0, nullable=False)
    duration_m2_minutes = Column(Numeric(14, 6), default=0, nullable=False)  # Welford M2
    start_hour_mean = Column(Numeric(8, 4), default=0, nullable=False)       # float timer, fx 7.5 = 07:30
    start_hour_m2 = Column(Numeric(12, 6), default=0, nullable=False)        # Welford M2
    salt_count = Column(Integer, default=0, nullable=False)                  # antal aktiviteter med salt
    last_updated = Column(DateTime, nullable=True)

    employee = relationship("Employee", back_populates="baselines")

    __table_args__ = (
        # Uden denne kan et race (to samtidige godkendelser af aktiviteter for
        # samme medarbejder+ugedag) skabe to baseline-rækker – hvilken af dem
        # der bruges bagefter afhænger så af forespørgselsrækkefølge, hvilket
        # giver inkonsistente auto-godkendelsesresultater.
        UniqueConstraint("employee_id", "weekday", name="uq_employee_baselines_employee_weekday"),
    )


class SystemSettings(Base):
    """Singleton-tabel (id altid 1) til globale systemindstillinger."""
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True)
    auto_approval_enabled = Column(Boolean, default=True, nullable=False, server_default="1")
    updated_by = Column(String, nullable=True)   # initialer på seneste bruger der ændrede
    updated_at = Column(DateTime, nullable=True)


class AppliedPermissionGrant(Base):
    """Husker hvilke opstarts-tildelinger af rettigheder (_ensure_*_permission i
    session.py) der allerede er kørt på denne database. En tildeling må kun ske
    ÉN gang – ellers ville en rettighed som en administrator bevidst har fjernet
    fra en rolle komme tilbage ved næste serverstart."""
    __tablename__ = "applied_permission_grants"

    key = Column(String, primary_key=True)
    applied_at = Column(DateTime, server_default=func.now())


class EmployeeSupplement(Base):
    __tablename__ = "employee_supplements"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False, default="Ikke overenskomstmæssigt tillæg")
    type = Column(String(50), nullable=False, default="Timebaseret")
    value = Column(Numeric(10, 2), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False, default=date(9999, 12, 31))
    created_at = Column(DateTime, server_default=func.now())

    employee = relationship("Employee")

    __table_args__ = (
        Index(
            "uq_employee_supplements_one_open_row",
            "employee_id",
            unique=True,
            sqlite_where=text("end_date = '9999-12-31'"),
        ),
    )


class EmployeeSpringerFlag(Base):
    __tablename__ = "employee_springer_flags"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False, index=True)
    pay_period_id = Column(Integer, ForeignKey("pay_periods.id"), nullable=False, index=True)
    enabled = Column(Boolean, default=False, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    updated_by = Column(String, nullable=True)

    employee = relationship("Employee")
    pay_period = relationship("PayPeriod")

    __table_args__ = (
        Index("uq_employee_springer_flags_emp_period", "employee_id", "pay_period_id", unique=True),
    )
