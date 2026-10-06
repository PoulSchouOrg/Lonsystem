import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from database.session import init_db
from routers import import_ddd, employees, activities, payroll_router, vehicles, employee_supplements, vagtplan_comments, payroll_settlement_router
from routers import auth as auth_router
from routers import users as users_router
from routers import roles as roles_router
from routers import absence_overview_router
from routers import timeseddel_router
from routers import stamdata as stamdata_router
from routers import dagsplan_router
from routers.auto_approval_router import router as auto_approval_router
from routers import elev_router
from routers import agreement_rates_router
from routers import alerts_router

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
ENTRA_TENANT_ID = os.getenv("ENTRA_TENANT_ID", "")
ENTRA_CLIENT_ID = os.getenv("ENTRA_CLIENT_ID", "")
if not SESSION_SECRET:
    raise RuntimeError(
        "SESSION_SECRET er ikke sat i .env – tilføj en stærk tilfældig nøgle "
        "(fx: python -c \"import secrets; print(secrets.token_hex(32))\")"
    )


class _SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' https://login.microsoftonline.com; "
            "frame-src https://login.microsoftonline.com;"
        )
        return response


def _check_overtime_rate_keys():
    """Verificerer at alle tre OT-nøgler eksisterer i DB (eller Excel som fallback)."""
    from database.session import SessionLocal
    from calculators.rates_loader import load_overtime_rates_from_db
    from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
    db = SessionLocal()
    try:
        rates = load_overtime_rates_from_db(db)
        missing = [k for k in (OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY) if k not in rates]
        if missing:
            logging.warning(
                f"ADVARSEL: Følgende overtidssats-nøgler mangler i stamdata: {missing}. "
                "Overtidsberegning vil returnere 0 kr. for disse typer. "
                "Gå til Stamdata → Overtidssatser og verificer nøglenavnene."
            )
    except Exception as e:
        logging.error(f"Kunne ikke kontrollere overtidssatser: {e}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _check_overtime_rate_keys()
    yield


app = FastAPI(title="Lønsystem", lifespan=lifespan)

app.add_middleware(_SecurityHeaders)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=86400, same_site="lax", https_only=False)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(roles_router.router)
app.include_router(import_ddd.router)
app.include_router(employees.router)
app.include_router(activities.router)
app.include_router(payroll_router.router)
app.include_router(payroll_settlement_router.router)
app.include_router(absence_overview_router.router)
app.include_router(timeseddel_router.router)
app.include_router(vehicles.router)
app.include_router(dagsplan_router.router)
app.include_router(dagsplan_router.vehicle_absence_router)
app.include_router(employee_supplements.router)
app.include_router(vagtplan_comments.router)
app.include_router(stamdata_router.router)
app.include_router(auto_approval_router)
app.include_router(elev_router.router)
app.include_router(agreement_rates_router.router)
app.include_router(alerts_router.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        # Højeste mtime af de to scripts, så en ændring i elev.js også bryder browser-cachen
        mtime = max(int((BASE_DIR / "static" / "js" / name).stat().st_mtime) for name in ("app.js", "elev.js", "agreement_rates.js", "alerts_overview.js"))
    except OSError:
        mtime = 0
    return templates.TemplateResponse("index.html", {
        "request": request,
        "app_js_mtime": mtime,
        "entra_tenant_id": ENTRA_TENANT_ID,
        "entra_client_id": ENTRA_CLIENT_ID,
    })


@app.get("/health")
async def health():
    return {"status": "ok"}
