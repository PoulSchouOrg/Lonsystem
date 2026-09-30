import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from sqlalchemy.orm import sessionmaker


def _roles(db):
    from database.models import Role
    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.add(Role(name="lonbogholder", display_name="Lønbogholder", is_system=False, permissions=[]))
    db.add(Role(name="kontor", display_name="Kontor", is_system=False, permissions=[]))
    db.commit()


def test_removed_permission_is_not_readded_on_next_startup(db, monkeypatch):
    """En rettighed en administrator har fjernet fra en rolle må ikke komme tilbage
    ved næste serverstart (tidligere blev _ensure_*-funktionerne kørt igen hver gang)."""
    import database.session as session_module
    from database.models import Role
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))
    _roles(db)

    session_module._ensure_activity_permissions()
    session_module._ensure_vagtplan_permissions()
    session_module._ensure_toggle_springer_permission()
    kontor = db.query(Role).filter(Role.name == "kontor").first()
    db.refresh(kontor)
    assert {"approve_activities", "view_calendar", "vagtplan_view",
            "vagtplan_edit_all", "toggle_springer"} <= set(kontor.permissions)

    # Administrator fjerner rettighederne fra Kontor
    kontor.permissions = ["vagtplan_view"]
    db.commit()

    # "Genstart"
    session_module._ensure_activity_permissions()
    session_module._ensure_vagtplan_permissions()
    session_module._ensure_toggle_springer_permission()
    db.refresh(kontor)
    assert kontor.permissions == ["vagtplan_view"]


def test_lonbogholder_grant_is_not_readded_after_removal(db, monkeypatch):
    import database.session as session_module
    from database.models import Role
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))
    _roles(db)

    session_module._ensure_anciennitet_alert_permission()
    lon = db.query(Role).filter(Role.name == "lonbogholder").first()
    db.refresh(lon)
    assert "anciennitet_alert" in lon.permissions
    kontor = db.query(Role).filter(Role.name == "kontor").first()
    db.refresh(kontor)
    assert "anciennitet_alert" not in kontor.permissions

    lon.permissions = []
    db.commit()
    session_module._ensure_anciennitet_alert_permission()
    db.refresh(lon)
    assert "anciennitet_alert" not in lon.permissions
