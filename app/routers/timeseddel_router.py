import io
import logging
from datetime import date, datetime
from html import escape as _esc

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from auth import require_permission
from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
from calculators.pay_rates import CVR_NUMBER
from database.models import AppUser, Employee, MasterCvrNumber
from database.session import get_db
from routers.payroll_router import _calculate_employee, _resolve_period


def _get_employee_cvr(emp: Employee, db: Session) -> str:
    if emp.cvr_number:
        return emp.cvr_number
    default = db.query(MasterCvrNumber).filter(MasterCvrNumber.is_default == True).first()
    if default:
        return default.cvr_number
    return CVR_NUMBER

router = APIRouter(prefix="/api/timeseddel", tags=["timeseddel"])
_access = require_permission("payroll")

_WEEKDAYS = ["Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag"]

PS_GREEN  = colors.HexColor('#317423')
PS_ACCENT = colors.HexColor('#78b21a')
GREY_BG   = colors.HexColor('#f5faf3')
PS_LIGHT  = colors.HexColor('#d4edcc')
GREY_ROW  = colors.HexColor('#f9f9f9')
GREY_LINE = colors.HexColor('#e8e8e8')
TOTAL_BG  = colors.HexColor('#eaf5e4')
WE_COLOR  = colors.HexColor('#f0f0f0')
WE_TEXT   = colors.HexColor('#aaaaaa')
DARK_GREY = colors.HexColor('#555555')

W = 257 * mm  # indholdbredde (A4 landscape - 40 mm margin)


def _enrich_days(days: list[dict]) -> list[dict]:
    for day in days:
        d = date.fromisoformat(day["date"])
        day["weekday"] = d.weekday()
    return days


def _fmt_date(iso: str) -> str:
    return f"{iso[8:10]}-{iso[5:7]}-{iso[0:4]}" if iso else ""


def _s(name, **kw):
    defaults = dict(fontName='Helvetica', fontSize=9, leading=12)
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)


def _p(text, style):
    return Paragraph(str(text), style)


def _fmt_hm(hours) -> str:
    """Timer som decimaltal -> 'Xt YYm' (fx 14.80 -> '14t 48m')."""
    h = float(hours)
    total_minutes = round(h * 60)
    hh = total_minutes // 60
    mm_ = total_minutes % 60
    return f'{hh}t {mm_:02d}m'


def _hm(val):
    try:
        h = float(val)
    except (TypeError, ValueError):
        return ''
    return _fmt_hm(h) if h > 0 else ''


def _kr(val) -> str:
    """Formaterer et kronebeløb med tusind-separator og dansk decimaltegn
    (fx 25.128,09) – bruges på alle beløbskolonner (DKK/Sats/Total kr./I alt)."""
    try:
        return f'{float(val):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    except (TypeError, ValueError):
        return '0,00'


def _vkr(val):
    try:
        return _kr(val) if val and float(val) > 0 else ''
    except (TypeError, ValueError):
        return ''


def _day_normal_hours(day: dict) -> float:
    """Timer der IKKE udløser noget overtidstillæg – day['normal'] indeholder alle
    arbejdede timer (tillæggene er additive, se calculators/overtime.py), så
    tillægstimerne (inkl. søgnehelligdagskode 8/9) trækkes fra. Samme formel som
    _build_proevekoersel_workbook() i payroll_router.py."""
    ot13 = day.get('ot_13', 0) + day.get('sh_kode8', 0)
    ot_extra = day.get('ot_extra', 0) + day.get('sh_kode9', 0)
    return round(day.get('normal', 0) - day.get('ot_before', 0) - ot13 - ot_extra, 2)


def _build_pdf(calc: dict, cvr_number: str = CVR_NUMBER) -> bytes:
    calc["days"] = _enrich_days(calc["days"])

    period_start = calc["days"][0]["date"] if calc["days"] else ""
    period_end   = calc["days"][-1]["date"] if calc["days"] else ""
    period_label = f"{_fmt_date(period_start)} – {_fmt_date(period_end)}"
    generated    = datetime.now().strftime("%d-%m-%Y %H:%M")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    s_body   = _s('body')
    s_right  = _s('right', alignment=TA_RIGHT)
    s_bold   = _s('bold', fontName='Helvetica-Bold')
    s_bold_r = _s('bold_r', fontName='Helvetica-Bold', alignment=TA_RIGHT)
    s_sub    = _s('sub', fontSize=8, textColor=DARK_GREY)
    s_sub_r  = _s('sub_r', fontSize=8, textColor=DARK_GREY, alignment=TA_RIGHT)
    s_sub_c  = _s('sub_c', fontSize=8, textColor=DARK_GREY, alignment=TA_CENTER)
    s_abs    = _s('abs', fontName='Helvetica-Oblique', textColor=DARK_GREY)
    s_h2     = _s('h2', fontName='Helvetica-Bold', fontSize=10, textColor=PS_GREEN)
    s_th     = _s('th', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white)
    s_th_r   = _s('th_r', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=TA_RIGHT)
    s_td     = _s('td', fontSize=8)
    s_td_r   = _s('td_r', fontSize=8, alignment=TA_RIGHT)
    s_td_we  = _s('td_we', fontSize=8, textColor=WE_TEXT)
    s_td_we_r = _s('td_we_r', fontSize=8, textColor=WE_TEXT, alignment=TA_RIGHT)
    s_td_abs = _s('td_abs', fontSize=8, fontName='Helvetica-Oblique', textColor=PS_GREEN)

    story = []

    # ── HEADER ──────────────────────────────────────────────────────
    hdr = Table([
        [_p('<font color="#317423"><b><font size="18">Poul Schou A/S</font></b></font>', s_body),
         _p(f'<b><font color="#317423" size="14">Timeseddel</font></b>', _s('htr', alignment=TA_RIGHT))],
        [_p(f'CVR: {cvr_number}', s_sub),
         _p(f'Periode: {period_label}<br/>Genereret: {generated}', s_sub_r)],
    ], colWidths=[W * 0.6, W * 0.4])
    hdr.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW',     (0, 1), (-1,  1), 2, PS_GREEN),
        ('TOPPADDING',    (0, 0), (-1,  0), 0),
        ('BOTTOMPADDING', (0, 0), (-1,  0), 2),
        ('BOTTOMPADDING', (0, 1), (-1,  1), 8),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 5 * mm))

    # ── MEDARBEJDERINFO ─────────────────────────────────────────────
    info = Table([
        [_p('Medarbejder', s_sub),      _p(_esc(calc['employee_name']), s_bold),
         _p('Lønnummer', s_sub),  _p(_esc(str(calc.get('employee_number', ''))), s_bold)],
        [_p('Overenskomsttype', s_sub), _p(_esc(str(calc.get('agreement_type', ''))), s_bold),
         _p('Timesats', s_sub),        _p(f"{_kr(calc['hourly_rate'])} kr/t", s_bold)],
    ], colWidths=[W * 0.20, W * 0.30, W * 0.20, W * 0.30])
    info.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), GREY_BG),
        ('BOX',           (0, 0), (-1, -1), 0.5, PS_LIGHT),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
    ]))
    story.append(info)
    story.append(Spacer(1, 5 * mm))

    # ── LØNOPSUMMERING ──────────────────────────────────────────────
    story.append(_p('LØNOPSUMMERING', s_h2))
    story.append(Spacer(1, 2 * mm))

    ot_rates       = calc.get('ot_rates', {})
    ot_before_rate = float(ot_rates.get(OT_BEFORE_KEY, 0))
    ot_13_rate     = float(ot_rates.get(OT_13_KEY, 0))
    ot_extra_rate  = float(ot_rates.get(OT_EXTRA_KEY, 0))
    hr             = float(calc.get('hourly_rate', 0))
    hrs            = calc.get('hourly_rates', {})

    sum_rows = [[_p('Type', s_th), _p('Antal', s_th_r), _p('Sats', s_th_r), _p('DKK', s_th_r)]]

    def add_row(label, hours, rate_str, dkk_str, absence=False):
        st = s_abs if absence else s_body
        sum_rows.append([_p(label, st), _p(_fmt_hm(hours), s_right),
                         _p(rate_str, s_right), _p(dkk_str, s_right)])

    # Fravær tæller med i "I alt", samme princip og satser som Lønafregningens
    # absence_kr_total (bekræftet af bruger 2026-08-25: "fravær skal ... tælle
    # med i totalen") – tidligere viste rækkerne kun timer og '–' i Sats/DKK.
    absence_kr_total = 0.0
    absence_hours_total = 0.0

    def add_absence_row(label, hours, rate):
        nonlocal absence_kr_total, absence_hours_total
        kr = hours * rate
        absence_kr_total += kr
        absence_hours_total += hours
        add_row(label, hours, f'{_kr(rate)} kr/t', _kr(kr), True)

    if calc.get('normal_hours', 0) > 0.001:
        h = float(calc['normal_hours'])
        add_row('Timer arbejdet', h, f'{_kr(hr)} kr/t', _kr(h * hr))
    springer_kr = 0.0
    if calc.get('springer_enabled') and calc.get('normal_hours', 0) > 0.001:
        h = float(calc['normal_hours'])
        springer_rate = float(calc.get('springer_rate', 0))
        springer_kr = h * springer_rate
        add_row('Springertillæg', h, f'{_kr(springer_rate)} kr/t', _kr(springer_kr))
    if calc.get('ot_before_hours', 0) > 0.001:
        h = float(calc['ot_before_hours'])
        add_row('Overtid 1 time før', h, f'{_kr(ot_before_rate)} kr/t', _kr(h * ot_before_rate))
    if calc.get('ot_13_hours', 0) > 0.001:
        h = float(calc['ot_13_hours'])
        add_row('Overtid 1–3 timer efter', h, f'{_kr(ot_13_rate)} kr/t', _kr(h * ot_13_rate))
    if calc.get('ot_extra_hours', 0) > 0.001:
        h = float(calc['ot_extra_hours'])
        add_row('Øvrig overtid', h, f'{_kr(ot_extra_rate)} kr/t', _kr(h * ot_extra_rate))
    if calc.get('salt_hours', 0) > 0.001:
        add_row('Salttillæg', float(calc['salt_hours']),
                f"{_kr(calc.get('salt_rate', 0))} kr/t",
                _kr(calc.get('salt_kr', 0)))
    dagpenge = float(calc.get('dagpenge_sats', 137.43))
    if calc.get('afspadsering_hours', 0) > 0.001:
        add_absence_row('Afspadsering', float(calc['afspadsering_hours']), hrs.get('afspadsering', hr))
    if calc.get('sygdom_hours', 0) > 0.001:
        add_absence_row('Sygdom', float(calc['sygdom_hours']), hrs.get('sygdom', hr))
    if calc.get('feriefri_hours', 0) > 0.001:
        add_absence_row('Feriefri', float(calc['feriefri_hours']), hrs.get('feriefri', hr))
    if calc.get('barsel_hours', 0) > 0.001:
        add_absence_row('Barsel', float(calc['barsel_hours']), hrs.get('barsel', hr))
    if calc.get('paragraf_56_syg_hours', 0) > 0.001:
        add_absence_row('§56 syg', float(calc['paragraf_56_syg_hours']), dagpenge)
    if calc.get('barn_1sygedag_u_loen_hours', 0) > 0.001:
        add_absence_row('Barn 1.sygedag u. løn', float(calc['barn_1sygedag_u_loen_hours']), dagpenge)
    if calc.get('skole_kursus_hours', 0) > 0.001:
        add_absence_row('Kursus/Skole', float(calc['skole_kursus_hours']), hrs.get('skole_kursus', hr))
    if calc.get('overnight_count', 0) > 0:
        count = int(calc['overnight_count'])
        rate  = float(calc.get('overnight_rate', 0))
        kr    = float(calc.get('overnight_kr', 0))
        sum_rows.append([
            _p('Overnatning', s_body),
            _p(f'{count} stk', s_right),
            _p(f'{_kr(rate)} kr/stk', s_right),
            _p(_kr(kr), s_right),
        ])
    if calc.get('dob_overnight_count', 0) > 0:
        count = int(calc['dob_overnight_count'])
        rate  = float(calc.get('dob_overnight_rate', 0))
        kr    = float(calc.get('dob_overnight_kr', 0))
        sum_rows.append([
            _p('DOB Overnatning', s_body),
            _p(f'{count} stk', s_right),
            _p(f'{_kr(rate)} kr/stk', s_right),
            _p(_kr(kr), s_right),
        ])

    total_display_kr = (
        float(calc.get('total_kr', 0))
        + float(calc.get('overnight_kr', 0))
        + float(calc.get('dob_overnight_kr', 0))
        + springer_kr
        + absence_kr_total
    )
    sum_rows.append([
        _p('I alt', s_bold),
        _p(_fmt_hm(float(calc.get('total_hours', 0)) + absence_hours_total), s_bold_r),
        _p('', s_body),
        _p(f"{_kr(total_display_kr)} kr", s_bold_r),
    ])

    sum_t = Table(sum_rows, colWidths=[W * 0.45, W * 0.18, W * 0.18, W * 0.19])
    sum_style = [
        ('BACKGROUND',    (0, 0), (-1,  0), PS_GREEN),
        ('FONTSIZE',      (0, 0), (-1, -1), 9),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
        ('BACKGROUND',    (0, -1), (-1, -1), TOTAL_BG),
        ('LINEABOVE',     (0, -1), (-1, -1), 1.5, PS_ACCENT),
        ('LINEBELOW',     (0,  0), (-1, -2), 0.3, GREY_LINE),
    ]
    for i in range(1, len(sum_rows) - 1):
        if i % 2 == 0:
            sum_style.append(('BACKGROUND', (0, i), (-1, i), GREY_ROW))
    sum_t.setStyle(TableStyle(sum_style))
    story.append(sum_t)
    story.append(Spacer(1, 5 * mm))

    # ── FOOTER (side 1) ─────────────────────────────────────────────
    footer = Table([[
        _p(f'Poul Schou A/S · CVR: {cvr_number}', s_sub),
        _p(f'{_esc(calc["employee_name"])} · {period_label}', s_sub_c),
        _p(f'Genereret {generated}', s_sub_r),
    ]], colWidths=[W / 3, W / 3, W / 3])
    footer.setStyle(TableStyle([
        ('LINEABOVE',  (0, 0), (-1, 0), 0.5, GREY_LINE),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
    ]))
    story.append(footer)

    # ── DAGSOVERSIGT ────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(_p('DAGSOVERSIGT', s_h2))
    story.append(Spacer(1, 2 * mm))

    # "Salt, timer"-kolonnen udelades helt, hvis ingen dage i perioden har salttillæg.
    has_salt = any((day.get('salt_hours') or 0) > 0.001 for day in calc['days'])

    headers = [
        _p('Dato', s_th),      _p('Dag', s_th),
        _p('Start', s_th_r),   _p('Slut', s_th_r),
        _p('Timer arbejdet', s_th_r), _p('Overtid før', s_th_r),
        _p('Overtid 1–3', s_th_r), _p('Øvrig overtid', s_th_r),
    ]
    widths_mm = [20, 15, 14, 14, 24, 22, 22, 24]
    if has_salt:
        headers.append(_p('Salt, timer', s_th_r))
        widths_mm.append(20)
    headers += [_p('Total antal', s_th_r), _p('Total kr.', s_th_r), _p('Fravær / Note', s_th)]
    widths_mm += [20, 18]

    day_rows = [headers]

    weekend_rows = []
    for i, day in enumerate(calc['days'], start=1):
        d        = day['date']
        date_str = _fmt_date(d)
        wday     = _WEEKDAYS[day['weekday']]
        is_we    = day['weekday'] >= 5
        absence  = day.get('absence_type') or ''

        note_parts = [absence] if absence else []
        if day.get('dob_overnight'):
            note_parts.append('DOB Overnatning')
        elif day.get('overnight'):
            note_parts.append('Overnatning')
        note = ', '.join(note_parts)

        if is_we:
            weekend_rows.append(i)
            cs, csr, ca = s_td_we, s_td_we_r, s_td_we
        elif note:
            cs, csr, ca = s_td, s_td_r, s_td_abs
        else:
            cs, csr, ca = s_td, s_td_r, s_td

        row = [
            _p(_esc(date_str), cs),        _p(_esc(wday), cs),
            _p(_esc(day.get('start_time') or ''), csr),
            _p(_esc(day.get('end_time') or ''),   csr),
            _p(_hm(_day_normal_hours(day)), csr),
            _p(_hm(day.get('ot_before')),   csr),
            _p(_hm(day.get('ot_13')),       csr),
            _p(_hm(day.get('ot_extra')),    csr),
        ]
        if has_salt:
            row.append(_p(_hm(day.get('salt_hours')), csr))
        # Fraværsdage har total_hours/total_kr = 0 (fraværstimer tæller ikke med
        # i loft-/overtidsberegningen) – de reelle timer/beløb ligger i stedet i
        # absence_hours/absence_kr, samme kilde som Lønafregningens dagsvisning
        # (_display_day i payroll_settlement_router.py), så "Total antal"/
        # "Total kr." også viser fravær her.
        disp_hours = day.get('absence_hours') if day.get('absence_hours') is not None else day.get('total_hours')
        disp_kr    = day.get('absence_kr')    if day.get('absence_hours') is not None else day.get('total_kr')
        row += [
            _p(_hm(disp_hours), csr),
            _p(_vkr(disp_kr),  csr),
            _p(_esc(note), ca),
        ]
        day_rows.append(row)

    fixed_w  = sum(widths_mm) * mm
    last_col = W - fixed_w
    cw = [w * mm for w in widths_mm] + [last_col]

    day_t = Table(day_rows, colWidths=cw)
    day_style = [
        ('BACKGROUND', (0, 0), (-1,  0), PS_GREEN),
        ('FONTSIZE',   (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING',   (0, 0), (-1, -1), 4),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
        ('LINEBELOW',     (0, 0), (-1, -1), 0.25, GREY_LINE),
    ]
    for i in range(1, len(day_rows)):
        if i % 2 == 0:
            day_style.append(('BACKGROUND', (0, i), (-1, i), GREY_ROW))
    for i in weekend_rows:
        day_style.append(('BACKGROUND', (0, i), (-1, i), WE_COLOR))
    day_t.setStyle(TableStyle(day_style))
    story.append(day_t)

    doc.build(story)
    return buf.getvalue()


@router.get("/{employee_id}/pdf")
def download_timeseddel(
    employee_id: int,
    period_start: str = Query(..., description="Periodestart YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(_access),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")

    period    = _resolve_period(period_start, db)
    calc      = _calculate_employee(emp, period.start_date, period.end_date, db)
    pdf_bytes = _build_pdf(calc, _get_employee_cvr(emp, db))

    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in emp.name)
    filename  = f"Timeseddel_{safe_name}_{period_start}.pdf"

    return Response(
        content    = pdf_bytes,
        media_type = "application/pdf",
        headers    = {"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _week_label(start: date, end: date) -> str:
    w1 = start.isocalendar()[1]
    w2 = end.isocalendar()[1]
    return f"uge {w1}" if w1 == w2 else f"uge {w1}-{w2}"


@router.post("/{employee_id}/send")
def send_timeseddel(
    employee_id: int,
    period_start: str = Query(..., description="Periodestart YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(_access),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    if not emp.email:
        raise HTTPException(400, f"{emp.name} har ingen e-mailadresse registreret")

    period       = _resolve_period(period_start, db)
    calc         = _calculate_employee(emp, period.start_date, period.end_date, db)
    pdf_bytes    = _build_pdf(calc, _get_employee_cvr(emp, db))
    period_label = f"{period.start_date.strftime('%d-%m-%Y')} – {period.end_date.strftime('%d-%m-%Y')}"
    week_label   = _week_label(period.start_date, period.end_date)

    try:
        from utils.email_sender import send_timeseddel as _send
        _send(
            to_email      = emp.email,
            employee_name = emp.name,
            period_label  = period_label,
            week_label    = week_label,
            pdf_bytes     = pdf_bytes,
        )
    except Exception as e:
        logging.error(f"Kunne ikke sende timeseddel til {emp.name} (id={emp.id}): {e}")
        raise HTTPException(500, "Mailen kunne ikke sendes – kontakt administrator")

    return {"ok": True, "sent_to": emp.email}


class SendAllRequest(BaseModel):
    from_date: date
    to_date: date
    employee_id: Optional[int] = None


@router.post("/send-all")
def send_all_timesedler(
    body: SendAllRequest,
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(_access),
):
    from utils.email_sender import send_timeseddel as _send_email

    if body.to_date < body.from_date:
        raise HTTPException(400, "Til-dato skal være efter fra-dato")

    q = db.query(Employee).filter(Employee.active == True)
    if body.employee_id:
        q = q.filter(Employee.id == body.employee_id)
    employees = q.order_by(Employee.first_name, Employee.last_name).all()

    period_label = f"{body.from_date.strftime('%d-%m-%Y')} – {body.to_date.strftime('%d-%m-%Y')}"
    week_label   = _week_label(body.from_date, body.to_date)

    sent = []
    skipped_no_email = []
    skipped_no_activities = []
    failed = []

    for emp in employees:
        if not emp.email:
            skipped_no_email.append(emp.name)
            continue
        calc = _calculate_employee(emp, body.from_date, body.to_date, db)
        if calc["activity_count"] == 0:
            skipped_no_activities.append(emp.name)
            continue
        pdf_bytes = _build_pdf(calc, _get_employee_cvr(emp, db))
        try:
            _send_email(
                to_email=emp.email,
                employee_name=emp.name,
                period_label=period_label,
                week_label=week_label,
                pdf_bytes=pdf_bytes,
            )
            sent.append(emp.name)
        except Exception as e:
            logging.error(f"Kunne ikke sende timeseddel til {emp.name} (id={emp.id}): {e}")
            failed.append({"name": emp.name, "error": "Kunne ikke sendes"})

    return {
        "sent": sent,
        "skipped_no_email": skipped_no_email,
        "skipped_no_activities": skipped_no_activities,
        "failed": failed,
    }
