"""Testmiljø (2026-10-07): rød TESTMILJØ-bjælke og aldrig e-mail, når LONSYSTEM_ENV=test.
I produktion (variablen ikke sat) ændres intet."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import pytest


def test_mail_blocked_in_test_env(monkeypatch):
    from utils import email_sender
    monkeypatch.setenv("LONSYSTEM_ENV", "test")
    monkeypatch.setenv("SMTP_USER", "x")
    monkeypatch.setenv("SMTP_PASSWORD", "y")
    sent = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", lambda *a, **k: sent.append(1))
    with pytest.raises(RuntimeError, match="slået fra i testmiljøet"):
        email_sender.send_timeseddel("a@b.dk", "Navn", "periode", b"%PDF")
    assert sent == []


def test_production_unchanged(monkeypatch):
    from utils.test_env import is_test_env
    monkeypatch.delenv("LONSYSTEM_ENV", raising=False)
    assert is_test_env() is False


def _render(test_env, source):
    import main
    return main.templates.get_template("index.html").render(
        request=None, app_js_mtime=0, entra_tenant_id="", entra_client_id="",
        test_env=test_env, test_data_source=source)


def test_banner_only_in_test_env():
    assert "TESTMILJØ" not in _render(False, None)
    html = _render(True, "07-10-2026 kl. 12:00")
    assert "TESTMILJØ – ikke rigtige lønkørsler" in html and "data fra backup 07-10-2026 kl. 12:00" in html


def test_index_passes_test_flags(monkeypatch):
    import inspect, main
    src = inspect.getsource(main.index)
    assert '"test_env": is_test_env()' in src and '"test_data_source": test_data_source()' in src
