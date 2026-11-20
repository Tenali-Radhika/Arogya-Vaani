"""Synthesize one code-mixed sentence through Murf's HTTP stream API to ./tmp/test.wav so you can listen.

Usage: python scripts/murf_say.py [locale]      e.g.  hi-IN (default) | kn-IN | en-IN
Docs : POST https://in.api.murf.ai/v1/speech/stream  (header: api-key)
"""
import os
import sys

import httpx
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env.local"))

SENTENCES = {
    "hi-IN": "आपका appointment कल सुबह साढ़े दस बजे Dr. Rao के साथ confirm हो गया है।",
    "kn-IN": "ನಿಮ್ಮ appointment ನಾಳೆ ಬೆಳಿಗ್ಗೆ ಹತ್ತೂವರೆಗೆ Dr. Rao ಅವರ ಜೊತೆ confirm ಆಗಿದೆ.",
    "en-IN": "Your appointment with Dr. Rao tomorrow at ten thirty is confirmed.",
}


def main() -> int:
    key, voice = os.getenv("MURF_API_KEY"), os.getenv("MURF_VOICE_ID")
    if not key or not voice:
        print("Set MURF_API_KEY and MURF_VOICE_ID in server/.env.local first (run murf_voices.py).")
        return 1
    locale = sys.argv[1] if len(sys.argv) > 1 else "hi-IN"
    body = {"text": SENTENCES[locale], "voiceId": voice, "model": "falcon-2.1", "locale": locale,
            "format": "WAV", "sampleRate": 24000}
    base = os.getenv("MURF_HTTP_BASE", "https://in.api.murf.ai").rstrip("/")
    r = httpx.post(f"{base}/v1/speech/stream", json=body, headers={"api-key": key}, timeout=30)
    if r.status_code != 200:
        print("Murf error:", r.status_code, r.text[:300])
        return 1
    out = os.path.join(HERE, "..", "..", "tmp", "test.wav")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(r.content)
    print(f"wrote {os.path.abspath(out)} ({len(r.content)} bytes) voice={voice} locale={locale}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
