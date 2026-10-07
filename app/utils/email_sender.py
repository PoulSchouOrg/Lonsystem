import os
import smtplib
import ssl
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

from utils.test_env import is_test_env

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _sanitize_header(value: str) -> str:
    return value.replace("\r", "").replace("\n", "").replace("\0", "")


def send_timeseddel(to_email: str, employee_name: str, period_label: str, pdf_bytes: bytes, week_label: str = ""):
    # Testmiljøet bruger rigtige data (kopi af backup) – der må aldrig gå e-mails til chaufførerne derfra.
    if is_test_env():
        raise RuntimeError("E-mail er slået fra i testmiljøet")
    host     = os.getenv("SMTP_HOST", "smtp.office365.com")
    port     = int(os.getenv("SMTP_PORT", "587"))
    user     = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    from_addr = os.getenv("SMTP_FROM", user)

    if not user or not password:
        raise ValueError("SMTP_USER og SMTP_PASSWORD skal være udfyldt i .env")

    safe_name_hdr   = _sanitize_header(employee_name)
    safe_period_hdr = _sanitize_header(period_label)

    msg = MIMEMultipart()
    msg["From"]    = from_addr
    msg["To"]      = to_email
    msg["Subject"] = f"Timeseddel – {safe_name_hdr} – {safe_period_hdr}"

    period_with_week = f"{period_label} ({week_label})" if week_label else period_label
    body = (
        f"Kære {employee_name},\n\n"
        f"Vedhæftet finder du din timeseddel for perioden {period_with_week}.\n\n"
        f"Ved spørgsmål til din timeseddel, besvar denne mail.\n\n"
        f"Med venlig hilsen\nPoul Schou A/S"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))

    safe_name   = "".join(c if c.isalnum() or c in " _-" else "_" for c in employee_name)
    safe_period = period_label.replace(" ", "_").replace("/", "-")
    filename = f"Timeseddel_{safe_name}_{safe_period}.pdf"

    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(user, password)
        server.sendmail(from_addr, [to_email], msg.as_bytes())
