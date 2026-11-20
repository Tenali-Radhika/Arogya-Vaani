"""Doctor directory + Bengaluru area geocoding (local table, optional Nominatim)."""
import json
import math
import os
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# Aliases (Roman + Devanagari + Kannada) -> canonical area name
AREA_ALIASES = {
    "jayanagar": "Jayanagar", "jaynagar": "Jayanagar", "जयनगर": "Jayanagar", "ಜಯನಗರ": "Jayanagar",
    "koramangala": "Koramangala", "कोरमंगला": "Koramangala", "ಕೋರಮಂಗಲ": "Koramangala",
    "whitefield": "Whitefield", "व्हाइटफील्ड": "Whitefield", "ವೈಟ್ಫೀಲ್ಡ್": "Whitefield",
    "malleshwaram": "Malleshwaram", "malleswaram": "Malleshwaram", "मल्लेश्वरम": "Malleshwaram", "ಮಲ್ಲೇಶ್ವರಂ": "Malleshwaram",
    "indiranagar": "Indiranagar", "इंदिरानगर": "Indiranagar", "ಇಂದಿರಾನಗರ": "Indiranagar",
    "hsr": "HSR Layout", "hsr layout": "HSR Layout",
    "rajajinagar": "Rajajinagar", "राजाजीनगर": "Rajajinagar", "ರಾಜಾಜಿನಗರ": "Rajajinagar",
    "yelahanka": "Yelahanka", "येलहंका": "Yelahanka", "ಯಲಹಂಕ": "Yelahanka",
}


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(os.path.join(_DATA, "doctors.json"), encoding="utf-8") as f:
        return json.load(f)


def doctors() -> List[dict]:
    return _load()["doctors"]


def get_doctor(doctor_id: str) -> Optional[dict]:
    return next((d for d in doctors() if d["id"] == doctor_id), None)


def areas() -> Dict[str, Tuple[float, float]]:
    return {k: tuple(v) for k, v in _load()["areas"].items()}


def canonical_area(text: str) -> Optional[str]:
    t = (text or "").strip().lower()
    for alias, name in AREA_ALIASES.items():
        if alias in t:
            return name
    return None


def geocode_area(text: str) -> Optional[dict]:
    name = canonical_area(text)
    if name:
        lat, lng = areas()[name]
        return {"area": name, "lat": lat, "lng": lng, "source": "local"}
    if os.getenv("GEOCODE_NOMINATIM") == "1":  # real-API path behind a flag
        import httpx
        try:
            r = httpx.get("https://nominatim.openstreetmap.org/search",
                          params={"q": f"{text}, Bengaluru", "format": "json", "limit": 1},
                          headers={"User-Agent": "arogyavaani-demo"}, timeout=8)
            j = r.json()
            if j:
                return {"area": text, "lat": float(j[0]["lat"]), "lng": float(j[0]["lon"]), "source": "nominatim"}
        except Exception:
            return None
    return None


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))
