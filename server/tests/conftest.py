"""Shared fixtures (standalone: no cloud, no creds)."""
import os
import sys
from datetime import date, timedelta

import httpx
import pytest
from fastapi import FastAPI

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

FAKE_ENV = {
    "AGORA_APP_ID": "0123456789abcdef0123456789abcdef",
    "AGORA_APP_CERTIFICATE": "fedcba9876543210fedcba9876543210",
    "CUSTOM_LLM_URL": "https://example.ngrok-free.dev/llm/chat/completions",
    "CUSTOM_LLM_API_KEY": "test-key",
    "CUSTOM_LLM_MODEL": "arogya-agent",
    "SARVAM_API_KEY": "sarvam-test", "MURF_API_KEY": "", "MURF_VOICE_ID": "TestVoice",
    "CLINIC_API_URL": "http://clinic.test/clinic/v1",
    "ASR_VENDOR": "sarvam",
}


def next_weekday_date(weekday_ok=(0, 1, 2, 3, 4)):
    d = date.today() + timedelta(days=1)
    while d.weekday() not in weekday_ok:
        d += timedelta(days=1)
    return d.isoformat()


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    for k, v in FAKE_ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("AROGYA_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "static"))
    for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "CONSOLE_PASSWORD", "LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    import db
    db.reset_engine()
    db.engine()
    yield
    db.reset_engine()


@pytest.fixture(autouse=True)
def clinic_transport():
    """Tools call the Clinic API over real HTTP semantics, served in-process via an ASGI transport."""
    import clinic_api
    import http_util
    from tools import handlers
    clinic_api._force_conflict["next"] = False
    handlers.PENDING_SWAPS.clear()
    capp = FastAPI()
    capp.include_router(clinic_api.router)
    http_util.set_transport(httpx.ASGITransport(app=capp))
    yield capp
    http_util.set_transport(None)


@pytest.fixture
def ctx():
    import db
    from tools.registry import ToolContext
    db.upsert_patient("p1", name="Lakshmi", age=62, area="Jayanagar", languages="kn,hi,en", caregiver_name="Ravi")
    db.update_call_session("s1", patient_id="p1", lang="hi-IN")
    return ToolContext(session_id="s1", patient_id="p1", lang="hi-IN")
