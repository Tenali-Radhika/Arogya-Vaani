"""List Murf Falcon voices that support hi-IN, kn-IN and en-IN (one persona across all demo languages).

Usage:  python scripts/murf_voices.py            (reads MURF_API_KEY from server/.env.local or the environment)
Docs :  GET https://api.murf.ai/v1/speech/voices?model=falcon-2.1   (header: api-key)
"""
import os
import sys

import httpx
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, "..", ".env.local"))
NEEDED = {"hi-IN", "kn-IN", "en-IN"}


def main() -> int:
    key = os.getenv("MURF_API_KEY")
    if not key:
        print("MURF_API_KEY missing (set it in server/.env.local)")
        return 1
    r = httpx.get("https://api.murf.ai/v1/speech/voices", params={"model": "falcon-2.1"},
                  headers={"api-key": key}, timeout=15)
    r.raise_for_status()
    voices = r.json()
    full = []
    for v in voices:
        locales = set((v.get("supportedLocales") or {}).keys()) | ({v["locale"]} if v.get("locale") else set())
        if NEEDED <= locales:
            full.append((v.get("gender") or "?", v.get("voiceId"), v.get("displayName"), sorted(locales),
                         {k: d.get("availableStyles") for k, d in (v.get("supportedLocales") or {}).items() if k in NEEDED}))
    print(f"{len(voices)} Falcon voices; {len(full)} support all of {sorted(NEEDED)}:\n")
    for g, vid, name, locs, styles in sorted(full):
        print(f"  {g:7} {vid:14} {name:14} locales={len(locs)}  styles={styles}")
    for gender in ("Female", "Male"):
        pick = next((f for f in full if f[0] == gender), None)
        if pick:
            print(f"\nRecommended {gender.lower()} voice: MURF_VOICE_ID={pick[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
