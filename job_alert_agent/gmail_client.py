"""Gmail API client — OAuth2 + helpers para leer alertas de empleo."""

import base64
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

# readonly para leer + send para mandar el digest diario
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

CREDENTIALS_FILE = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GMAIL_TOKEN_FILE", "token.json")


def _resolve_path(filename: str) -> Path:
    """Resuelve paths relativos desde el directorio de este archivo."""
    p = Path(filename)
    if p.is_absolute():
        return p
    return Path(__file__).parent / filename


def get_gmail_service():
    """Devuelve un servicio Gmail autenticado. Refresca el token si expiró."""
    token_path = _resolve_path(TOKEN_FILE)
    creds_path = _resolve_path(CREDENTIALS_FILE)

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                raise FileNotFoundError(
                    f"No encontré {creds_path}. "
                    "Corré primero: python setup_auth.py"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json())
        print(f"Token guardado en {token_path}")

    return build("gmail", "v1", credentials=creds)


def _decode_body(part: dict) -> str:
    """Decodifica base64url a string."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")


def _extract_text(payload: dict) -> str:
    """Extrae texto plano (o HTML como fallback) de un payload MIME."""
    mime = payload.get("mimeType", "")

    if mime == "text/plain":
        return _decode_body(payload)

    if mime == "text/html":
        raw_html = _decode_body(payload)
        try:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            return h.handle(raw_html)
        except ImportError:
            # Fallback básico sin librería
            return re.sub(r"<[^>]+>", " ", raw_html)

    # Multipart: recorre las partes recursivamente
    for part in payload.get("parts", []):
        text = _extract_text(part)
        if text.strip():
            return text

    return ""


def fetch_job_alert_emails(days_lookback: int = 1) -> list[dict]:
    """
    Busca emails de alertas de empleo de los últimos `days_lookback` días.

    Retorna lista de dicts con:
      - id, subject, sender, date, body_text, snippet
    """
    service = get_gmail_service()

    # Fecha mínima en formato Gmail (YYYY/MM/DD)
    since = datetime.now(timezone.utc) - timedelta(days=days_lookback)
    since_str = since.strftime("%Y/%m/%d")

    # Consulta que cubre las principales fuentes de alertas de empleo
    query = (
        f"after:{since_str} "
        "("
        'subject:"alerta de empleo" OR '
        'subject:"job alert" OR '
        'subject:"new jobs for you" OR '
        'subject:"nuevas ofertas" OR '
        'from:jobalerts-noreply@linkedin.com OR '
        'from:alert@glassdoor.com OR '
        'from:noreply@indeed.com OR '
        'from:jobs-noreply@linkedin.com OR '
        'from:alertas@bumeran.com.ar OR '
        'from:alertas@zonajobs.com.ar OR '
        'from:info@getonbrd.com'
        ")"
    )

    try:
        results = service.users().messages().list(
            userId="me", q=query, maxResults=100
        ).execute()
    except HttpError as e:
        print(f"Error consultando Gmail: {e}")
        return []

    messages = results.get("messages", [])
    if not messages:
        print(f"No se encontraron alertas de empleo desde {since_str}.")
        return []

    emails = []
    for msg_ref in messages:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_ref["id"], format="full"
            ).execute()
        except HttpError as e:
            print(f"Error leyendo mensaje {msg_ref['id']}: {e}")
            continue

        headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}
        body_text = _extract_text(msg["payload"])

        emails.append({
            "id": msg["id"],
            "subject": headers.get("subject", "(sin asunto)"),
            "sender": headers.get("from", ""),
            "date": headers.get("date", ""),
            "snippet": msg.get("snippet", ""),
            "body_text": body_text,
        })

    print(f"Se encontraron {len(emails)} alertas de empleo.")
    return emails


def send_email(to: str, subject: str, html_body: str) -> None:
    """Envía un email HTML desde la cuenta autenticada."""
    import email.mime.multipart
    import email.mime.text

    service = get_gmail_service()

    message = email.mime.multipart.MIMEMultipart("alternative")
    message["to"] = to
    message["subject"] = subject
    message.attach(email.mime.text.MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    print(f"Digest enviado a {to}")
