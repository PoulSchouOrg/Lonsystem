from database.schemas import EmployeeCreate, WorkSchedule
from datetime import date


def test_employee_response_includes_initials(db, employee):
    from routers.employees import _to_response
    employee.initials = "ABC"
    db.commit()
    resp = _to_response(employee, db)
    assert resp.initials == "ABC"


def test_employee_initials_defaults_to_none(db, employee):
    from routers.employees import _to_response
    resp = _to_response(employee, db)
    assert resp.initials is None


def test_create_employee_persists_initials(db):
    from routers.employees import create_employee
    from database.models import AppUser, MasterAgreementType, MasterAgreementKind
    from decimal import Decimal
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.commit()
    body = EmployeeCreate(
        employee_number="9999",
        first_name="Ny",
        last_name="Person",
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
        initials="NYP",
    )
    user = AppUser(name="Test", initials="TST", role="admin", password_hash="x")
    resp = create_employee(body, current_user=user, db=db)
    assert resp.initials == "NYP"


from database.models import ActivitySource, ActivityStatus, Activity, AppUser
from database.schemas import ActivityCreate
from datetime import datetime
from fastapi import HTTPException
import pytest


def _dummy_user(role="admin", initials="TST"):
    return AppUser(name="Test", initials=initials, role=role, password_hash="x")


def test_user_has_permission_true_for_system_role(db):
    from auth import user_has_permission
    from database.models import Role
    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.commit()
    assert user_has_permission(db, _dummy_user(role="admin"), "vagtplan_edit_all") is True


def test_user_has_permission_checks_role_permission_list(db):
    from auth import user_has_permission
    from database.models import Role
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=["vagtplan_view"]))
    db.commit()
    user = _dummy_user(role="disponent")
    assert user_has_permission(db, user, "vagtplan_view") is True
    assert user_has_permission(db, user, "vagtplan_edit_all") is False


def test_create_activity_with_vagtplan_source_requires_edit_all_or_own(db, employee):
    from routers.activities import create_manual_activity
    from database.models import Role
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=[]))
    db.commit()
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="ferie",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 14, 0),
        source="vagtplan",
    )
    with pytest.raises(HTTPException) as exc:
        create_manual_activity(body, current_user=_dummy_user(role="disponent"), db=db)
    assert exc.value.status_code == 403


def test_create_activity_with_vagtplan_source_succeeds_with_edit_all(db, employee):
    from routers.activities import create_manual_activity
    from database.models import Role
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=["vagtplan_edit_all"]))
    db.commit()
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="ferie",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 14, 0),
        source="vagtplan",
    )
    resp = create_manual_activity(body, current_user=_dummy_user(role="disponent"), db=db)
    assert resp.source == ActivitySource.vagtplan


def test_create_activity_with_vagtplan_source_succeeds_with_edit_own_matching_initials(db, employee):
    from routers.activities import create_manual_activity
    from database.models import Role
    employee.initials = "ABC"
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=["vagtplan_edit_own"]))
    db.commit()
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="ferie",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 14, 0),
        source="vagtplan",
    )
    resp = create_manual_activity(body, current_user=_dummy_user(role="disponent", initials="abc"), db=db)
    assert resp.source == ActivitySource.vagtplan


def test_create_activity_without_vagtplan_source_is_unaffected(db, employee):
    """Aktivitetsoversigtens almindelige oprettelse (ingen 'source' i body) skal stadig
    virke uden nogen permission-tjek, uændret fra før denne opgave."""
    from routers.activities import create_manual_activity
    body = ActivityCreate(
        employee_id=employee.id,
        activity_type="normal",
        start_time=datetime(2026, 1, 5, 6, 0),
        end_time=datetime(2026, 1, 5, 14, 0),
    )
    resp = create_manual_activity(body, current_user=_dummy_user(), db=db)
    assert resp.source == ActivitySource.manual


def test_activity_response_includes_hidden_from_vagtplan_default_false(db, employee):
    from routers.activities import _to_response
    from calculators.pay_period import get_or_create_period_for_date
    period = get_or_create_period_for_date(datetime(2026, 1, 5).date(), db)
    a = Activity(employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.manual,
                 activity_type="ferie", start_time=datetime(2026, 1, 5, 6, 0),
                 end_time=datetime(2026, 1, 5, 14, 0), status=ActivityStatus.approved,
                 pause_intervals=[], segments=[])
    db.add(a)
    db.commit()
    assert _to_response(a).hidden_from_vagtplan is False


def test_hide_from_vagtplan_sets_flag_without_deleting_row(db, employee):
    from routers.activities import hide_from_vagtplan
    from database.schemas import VagtplanHideBody
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import Role
    # Kræver redigeringsret i Vagtplanen (håndhævet i backend siden 2026-09-30)
    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    period = get_or_create_period_for_date(datetime(2026, 1, 5).date(), db)
    a = Activity(employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.vagtplan,
                 activity_type="ferie", start_time=datetime(2026, 1, 5, 6, 0),
                 end_time=datetime(2026, 1, 5, 14, 0), status=ActivityStatus.deactivated,
                 pause_intervals=[], segments=[])
    db.add(a)
    db.commit()
    resp = hide_from_vagtplan(a.id, VagtplanHideBody(hidden=True), current_user=_dummy_user(), db=db)
    assert resp.hidden_from_vagtplan is True
    db.refresh(a)
    assert a.status == ActivityStatus.deactivated  # rækken/status upåvirket


def test_reopen_resets_hidden_from_vagtplan(db, employee):
    from routers.activities import reopen_activity
    from calculators.pay_period import get_or_create_period_for_date
    period = get_or_create_period_for_date(datetime(2026, 1, 5).date(), db)
    a = Activity(employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.vagtplan,
                 activity_type="ferie", start_time=datetime(2026, 1, 5, 6, 0),
                 end_time=datetime(2026, 1, 5, 14, 0), status=ActivityStatus.deactivated,
                 hidden_from_vagtplan=True, pause_intervals=[], segments=[])
    db.add(a)
    db.commit()
    resp = reopen_activity(a.id, current_user=_dummy_user(), db=db)
    assert resp.hidden_from_vagtplan is False


def test_list_activities_date_range_returns_only_overlapping_activities(db, employee):
    from routers.activities import list_activities
    from conftest import make_activity
    make_activity(db, employee, datetime(2026, 1, 5, 8, 0), datetime(2026, 1, 5, 16, 0))
    make_activity(db, employee, datetime(2026, 2, 20, 8, 0), datetime(2026, 2, 20, 16, 0))
    result = list_activities(date_from="2026-01-01", date_to="2026-01-31",
                              current_user=_dummy_user(), db=db)
    assert len(result) == 1
    assert result[0].start_time.month == 1


def test_list_activities_date_range_includes_activity_crossing_range_end(db, employee):
    from routers.activities import list_activities
    from conftest import make_activity
    make_activity(db, employee, datetime(2026, 1, 31, 22, 0), datetime(2026, 2, 1, 4, 0))
    result = list_activities(date_from="2026-01-01", date_to="2026-01-31",
                              current_user=_dummy_user(), db=db)
    assert len(result) == 1


def test_list_activities_date_range_respects_employee_filter(db, employee):
    from routers.activities import list_activities
    from conftest import make_activity
    from database.models import Employee, AgreementKind
    from datetime import date as _date
    other = Employee(employee_number="2002", first_name="Anden", last_name="Person",
                     agreement_kind=AgreementKind.hourly_fixed, agreement_type="Standardoverenskomst",
                     hire_date=_date(2020, 1, 1), work_schedule={"even": [0]*7, "odd": [0]*7})
    db.add(other)
    db.commit()
    make_activity(db, employee, datetime(2026, 1, 5, 8, 0), datetime(2026, 1, 5, 16, 0))
    make_activity(db, other, datetime(2026, 1, 6, 8, 0), datetime(2026, 1, 6, 16, 0))
    result = list_activities(date_from="2026-01-01", date_to="2026-01-31", employee_id=employee.id,
                              current_user=_dummy_user(), db=db)
    assert len(result) == 1
    assert result[0].employee_id == employee.id


def test_all_permissions_includes_vagtplan_keys():
    from auth import ALL_PERMISSIONS
    assert "vagtplan_view" in ALL_PERMISSIONS
    assert "vagtplan_edit_own" in ALL_PERMISSIONS
    assert "vagtplan_edit_all" in ALL_PERMISSIONS


def test_ensure_vagtplan_permissions_adds_view_and_edit_all_to_all_roles(db, monkeypatch):
    from database.models import Role
    from database.session import _ensure_vagtplan_permissions
    import database.session as session_module
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    db.add(Role(name="lonbogholder", display_name="Lønbogholder", is_system=False, permissions=["payroll"]))
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=[]))
    db.commit()

    _ensure_vagtplan_permissions()

    for role in db.query(Role).all():
        db.refresh(role)
        assert "vagtplan_view" in role.permissions
        assert "vagtplan_edit_all" in role.permissions
        assert "vagtplan_edit_own" not in role.permissions  # kun tilføjet automatisk, ikke opt-in

    # Idempotent
    _ensure_vagtplan_permissions()
    for role in db.query(Role).all():
        db.refresh(role)
        assert role.permissions.count("vagtplan_view") == 1


def test_create_vagtplan_comment_requires_edit_permission(db, employee):
    from routers.vagtplan_comments import create_comment
    from database.schemas import VagtplanCommentCreate
    from database.models import Role
    from datetime import date as _date
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=[]))
    db.commit()
    body = VagtplanCommentCreate(employee_id=employee.id, date=_date(2026, 1, 5), text="Ringer syg ind")
    with pytest.raises(HTTPException) as exc:
        create_comment(body, current_user=_dummy_user(role="disponent"), db=db)
    assert exc.value.status_code == 403


def test_create_vagtplan_comment_upserts_on_same_employee_and_date(db, employee):
    from routers.vagtplan_comments import create_comment
    from database.schemas import VagtplanCommentCreate
    from database.models import Role
    from datetime import date as _date
    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.commit()
    user = _dummy_user(role="admin")
    body1 = VagtplanCommentCreate(employee_id=employee.id, date=_date(2026, 1, 5), text="Første tekst")
    resp1 = create_comment(body1, current_user=user, db=db)
    body2 = VagtplanCommentCreate(employee_id=employee.id, date=_date(2026, 1, 5), text="Rettet tekst")
    resp2 = create_comment(body2, current_user=user, db=db)
    assert resp1.id == resp2.id
    assert resp2.text == "Rettet tekst"

    from database.models import VagtplanComment
    assert db.query(VagtplanComment).count() == 1


def test_list_comments_filters_by_date_range(db, employee):
    from routers.vagtplan_comments import create_comment, list_comments
    from database.schemas import VagtplanCommentCreate
    from database.models import Role
    from datetime import date as _date
    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.commit()
    user = _dummy_user(role="admin")
    create_comment(VagtplanCommentCreate(employee_id=employee.id, date=_date(2026, 1, 5), text="Inden for"), current_user=user, db=db)
    create_comment(VagtplanCommentCreate(employee_id=employee.id, date=_date(2026, 3, 1), text="Uden for"), current_user=user, db=db)
    result = list_comments(date_from="2026-01-01", date_to="2026-01-31", employee_id=None,
                            current_user=user, db=db)
    assert len(result) == 1
    assert result[0].text == "Inden for"


def test_delete_comment_requires_edit_permission(db, employee):
    from routers.vagtplan_comments import create_comment, delete_comment
    from database.schemas import VagtplanCommentCreate
    from database.models import Role
    from datetime import date as _date
    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=[]))
    db.commit()
    admin = _dummy_user(role="admin")
    comment = create_comment(VagtplanCommentCreate(employee_id=employee.id, date=_date(2026, 1, 5), text="X"), current_user=admin, db=db)
    with pytest.raises(HTTPException) as exc:
        delete_comment(comment.id, current_user=_dummy_user(role="disponent"), db=db)
    assert exc.value.status_code == 403
    delete_comment(comment.id, current_user=admin, db=db)
    from database.models import VagtplanComment
    assert db.query(VagtplanComment).count() == 0


def test_delete_activity_removes_row_permanently(db, employee):
    from routers.activities import create_manual_activity, delete_activity
    from database.schemas import ActivityCreate
    from database.models import Role, Activity
    from datetime import datetime as _dt
    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.commit()
    admin = _dummy_user(role="admin")
    body = ActivityCreate(
        employee_id=employee.id, activity_type="ferie",
        start_time=_dt(2026, 1, 5, 6, 0), end_time=_dt(2026, 1, 5, 14, 0),
        source="vagtplan",
    )
    a = create_manual_activity(body, current_user=admin, db=db)
    activity_id = a.id
    delete_activity(activity_id, current_user=admin, db=db)
    assert db.query(Activity).filter(Activity.id == activity_id).first() is None


def test_delete_activity_allows_absence_regardless_of_source(db, employee):
    """Sletning skal virke for enhver fraværstype, uanset om den er oprettet manuelt
    via Aktivitetsoversigten (source=manual) eller via Vagtplan – bekræftet af bruger
    2026-09-04, som udvidede den oprindelige vagtplan-kun-begrænsning."""
    from routers.activities import create_manual_activity, delete_activity
    from database.schemas import ActivityCreate
    from database.models import Activity
    from datetime import datetime as _dt
    body = ActivityCreate(
        employee_id=employee.id, activity_type="ferie",
        start_time=_dt(2026, 1, 5, 6, 0), end_time=_dt(2026, 1, 5, 14, 0),
    )
    a = create_manual_activity(body, current_user=_dummy_user(), db=db)
    assert a.source == "manual"
    delete_activity(a.id, current_user=_dummy_user(), db=db)
    assert db.query(Activity).filter(Activity.id == a.id).first() is None


def test_delete_activity_allows_manually_created_normal_activity(db, employee):
    from routers.activities import create_manual_activity, delete_activity
    from database.schemas import ActivityCreate
    from database.models import Activity
    from datetime import datetime as _dt
    body = ActivityCreate(
        employee_id=employee.id, activity_type="normal",
        start_time=_dt(2026, 1, 5, 6, 0), end_time=_dt(2026, 1, 5, 14, 0),
        vehicle_number="2321",
    )
    a = create_manual_activity(body, current_user=_dummy_user(), db=db)
    assert a.source == ActivitySource.manual
    delete_activity(a.id, current_user=_dummy_user(), db=db)
    assert db.query(Activity).filter(Activity.id == a.id).first() is None


def test_delete_activity_rejects_tachograph_normal_activity(db, employee):
    from routers.activities import delete_activity
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import Activity
    from datetime import datetime as _dt
    period = get_or_create_period_for_date(_dt(2026, 1, 5).date(), db)
    a = Activity(
        employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.tachograph,
        activity_type="normal", start_time=_dt(2026, 1, 5, 6, 0), end_time=_dt(2026, 1, 5, 14, 0),
        status=ActivityStatus.pending, pause_intervals=[], segments=[],
    )
    db.add(a)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        delete_activity(a.id, current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 400


def test_delete_activity_rejects_unknown_id(db):
    from routers.activities import delete_activity
    with pytest.raises(HTTPException) as exc:
        delete_activity(999999, current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 404


def test_delete_activity_rejects_split_activity(db, employee):
    from routers.activities import create_manual_activity, split_activity, delete_activity
    from database.schemas import ActivityCreate, ActivitySplit
    from database.models import Role
    from datetime import datetime as _dt
    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.commit()
    admin = _dummy_user(role="admin")
    body = ActivityCreate(
        employee_id=employee.id, activity_type="ferie",
        start_time=_dt(2026, 1, 5, 6, 0), end_time=_dt(2026, 1, 5, 14, 0),
        source="vagtplan",
    )
    a = create_manual_activity(body, current_user=admin, db=db)
    split_activity(a.id, ActivitySplit(split_at=_dt(2026, 1, 5, 10, 0)), current_user=admin, db=db)
    with pytest.raises(HTTPException) as exc:
        delete_activity(a.id, current_user=admin, db=db)
    assert exc.value.status_code == 400
