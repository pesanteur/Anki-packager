# api/download.py
import base64, json, re, hashlib, tempfile, os
from typing import List, Literal, Optional
from fastapi import FastAPI, Response, HTTPException
from pydantic import BaseModel

app = FastAPI()

NoteType = Literal["Basic", "Basic (and reverse)", "Cloze"]

class Card(BaseModel):
    note_type: NoteType
    front: Optional[str] = None
    back: Optional[str] = None
    text: Optional[str] = None
    tags: Optional[List[str]] = None

class BuildPayload(BaseModel):
    deck_name: Optional[str] = "Learning AI"
    cards: List[Card]

# import the same builders from build_apkg.py
from .build_apkg import build_apkg_bytes  # type: ignore

@app.get("/")
def download(payload: str):
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        bp = BuildPayload(**data)
    except Exception:
        raise HTTPException(status_code=400, detail="Bad payload")

    content = build_apkg_bytes(bp.deck_name or "Learning AI", bp.cards)
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", f"{bp.deck_name}.apkg") or "deck.apkg"
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe}"'}
    )