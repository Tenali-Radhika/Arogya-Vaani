"""Tiny RAG over data/kb/*.md (BM25 over bullet chunks, with cross-lingual keyword expansion)."""
import glob
import os
import re
from functools import lru_cache
from typing import List

from rank_bm25 import BM25Okapi

_KB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "kb")

# Map common Hindi/Kannada query words to English KB vocabulary.
EXPAND = {
    "sugar": "blood sugar fasting test", "शुगर": "blood sugar fasting test", "खाली पेट": "fasting",
    "ಸಕ್ಕರೆ": "blood sugar fasting", "ayushman": "pm-jay ayushman card", "आयुष्मान": "pm-jay ayushman card",
    "ಆಯುಷ್ಮಾನ್": "pm-jay ayushman card", "report": "old reports bring", "रिपोर्ट": "old reports bring",
    "xray": "x-ray old reports", "x-ray": "x-ray old reports", "एक्स-रे": "x-ray old reports",
    "cancel": "cancel reschedule", "fee": "fee consultation", "फीस": "fee consultation", "ಶುಲ್ಕ": "fee consultation",
    "tayari": "preparation prepare", "तैयारी": "preparation prepare", "ತಯಾರಿ": "preparation prepare",
    "knee": "orthopaedics knee x-ray", "घुटने": "orthopaedics knee x-ray", "ghutne": "orthopaedics knee x-ray",
}


def _tok(s: str) -> List[str]:
    return re.findall(r"\w+", s.lower())


@lru_cache(maxsize=1)
def _index():
    chunks = []
    for path in sorted(glob.glob(os.path.join(_KB, "*.md"))):
        src = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("- "):
                    chunks.append({"source": src, "text": line[2:]})
    return BM25Okapi([_tok(c["text"]) for c in chunks]), chunks


def retrieve(query: str, k: int = 3) -> List[dict]:
    q = query.lower()
    for key, extra in EXPAND.items():
        if key in q:
            q += " " + extra
    bm25, chunks = _index()
    scores = bm25.get_scores(_tok(q))
    ranked = sorted(zip(scores, chunks), key=lambda x: -x[0])
    return [{"text": c["text"], "source": c["source"], "score": round(float(s), 3)}
            for s, c in ranked[:k] if s > 0]
