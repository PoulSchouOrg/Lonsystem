import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date

from database.models import Base, Employee, Activity, ActivitySource, ActivityStatus, AgreementKind
from calculators.pay_period import get_or_create_period_for_date


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_activity_permissions: håndhæv approve_activities/edit_activities i testen",
    )


@pytest.fixture(autouse=True)
def _allow_activity_permissions(request, monkeypatch):
    """De fleste tests kalder aktivitets-endpoints med en dummy-bruger uden rolle i
    test-databasen. Rettighedstjekket for approve_activities/edit_activities slås
    derfor fra som standard – tests af selve tjekket markeres
    @pytest.mark.real_activity_permissions."""
    if request.node.get_closest_marker("real_activity_permissions"):
        return
    import routers.activities as activities_router
    monkeypatch.setattr(activities_router, "_has_activity_permission", lambda *a, **k: True)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def employee(db):
    emp = Employee(
        employee_number="1001",
        first_name="Test",
        last_name="Chauffør",
        agreement_kind=AgreementKind.hourly_fixed,
        agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


def make_activity(db, employee, start: datetime, end: datetime,
                  activity_type="normal", source=ActivitySource.tachograph,
                  salt_supplement=False, status=ActivityStatus.pending):
    period = get_or_create_period_for_date(start.date(), db)
    act = Activity(
        employee_id=employee.id,
        pay_period_id=period.id,
        source=source,
        activity_type=activity_type,
        start_time=start,
        end_time=end,
        salt_supplement=salt_supplement,
        status=status,
        pause_intervals=[],
        segments=[],
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


def set_auto_approval_enabled(db, enabled: bool):
    """Testhjælper: opret/opdater singleton SystemSettings-recorden direkte."""
    from database.models import SystemSettings
    settings = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if settings is None:
        settings = SystemSettings(id=1, auto_approval_enabled=enabled)
        db.add(settings)
    else:
        settings.auto_approval_enabled = enabled
    db.commit()
    return settings
