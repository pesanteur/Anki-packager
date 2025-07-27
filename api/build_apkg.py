# api/build_apkg.py
import base64, hashlib, json, re, tempfile, os
from typing import List, Literal, Optional
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field, validator

app = FastAPI()

NoteType = Literal["Basic", "Basic (and reverse)", "Cloze"]

class Card(BaseModel):
    note_type: NoteType
    front: Optional[str] = None
    back: Optional[str] = None
    text: Optional[str] = None
    tags: Optional[List[str]] = None

    @validator("front", always=False)
    def v_front(cls, v, values):
        if values.get("note_type") in ["Basic","Basic (and reverse)"] and not v:
            raise ValueError("front required for Basic/Reverse")
        return v

    @validator("back", always=False)
    def v_back(cls, v, values):
        if values.get("note_type") in ["Basic","Basic (and reverse)"] and not v:
            raise ValueError("back required for Basic/Reverse")
        return v

    @validator("text", always=False)
    def v_text(cls, v, values):
        if values.get("note_type") == "Cloze" and not v:
            raise ValueError("text required for Cloze")
        if v:
            n = len(re.findall(r"{{c\d+::", v))
            if n > 2:
                raise ValueError(f"Cloze has {n} deletions; max is 2")
        return v

class BuildRequest(BaseModel):
    deck_name: Optional[str] = Field(default="Learning AI")
    cards: List[Card]

def kebab(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def normalize_tags(tags: Optional[List[str]]) -> List[str]:
    out = []
    for t in (tags or []):
        if ":" in t:
            k, v = t.split(":", 1)
            out.append(f"{k}:{kebab(v)}")
        else:
            out.append(kebab(t))
    return out

def build_apkg_bytes(deck_name: str, cards: List[Card]) -> bytes:
    import genanki
    deck_id = int(hashlib.sha256(deck_name.encode("utf-8")).hexdigest()[:12], 16)

    BASIC_MODEL_ID = 1607392319
    REVERSE_MODEL_ID = BASIC_MODEL_ID + 1
    CLOZE_MODEL_ID = 998877665

    basic_model = genanki.Model(
        BASIC_MODEL_ID, "Basic",
        fields=[{"name":"Front"},{"name":"Back"}],
        templates=[{"name":"Card 1","qfmt":"{{Front}}","afmt":"{{FrontSide}}<hr id=\"answer\">{{Back}}"}],
        css=".card { font-family: arial; font-size: 16px; text-align: left; }",
    )
    reverse_model = genanki.Model(
        REVERSE_MODEL_ID, "Basic (and reverse)",
        fields=[{"name":"Front"},{"name":"Back"}],
        templates=[
            {"name":"Forward","qfmt":"{{Front}}","afmt":"{{FrontSide}}<hr id=\"answer\">{{Back}}"},
            {"name":"Reverse","qfmt":"{{Back}}","afmt":"{{Back}}<hr id=\"answer\">{{Front}}"},
        ],
        css=".card { font-family: arial; font-size: 16px; text-align: left; }",
    )
    cloze_model = genanki.Model(
        CLOZE_MODEL_ID, "Cloze",
        fields=[{"name":"Text"}],
        templates=[{"name":"Cloze","qfmt":"{{cloze:Text}}","afmt":"{{cloze:Text}}"}],
        css=".card { font-family: arial; font-size: 16px; text-align: left; }",
        model_type=genanki.Model.CLOZE,
    )

    deck = genanki.Deck(deck_id, deck_name)
    for c in cards:
        tags = normalize_tags(c.tags)
        if c.note_type == "Basic":
            note = genanki.Note(model=basic_model, fields=[c.front, c.back], tags=tags)
        elif c.note_type == "Basic (and reverse)":
            note = genanki.Note(model=reverse_model, fields=[c.front, c.back], tags=tags)
        else:
            note = genanki.Note(model=cloze_model, fields=[c.text], tags=tags)
        deck.add_note(note)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".apkg", dir="/tmp")
    tmp.close()
    try:
        genanki.Package(deck).write_to_file(tmp.name)
        with open(tmp.name, "rb") as f:
            return f.read()
    finally:
        try: os.remove(tmp.name)
        except OSError: pass

# Accept both "/api/build_apkg" and "/"
@app.post("/")
@app.post("/api/build_apkg")
def build(req: BuildRequest, request: Request):
    payload = {
        "deck_name": req.deck_name or "Learning AI",
        "cards": [c.model_dump() for c in req.cards],
    }
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    # Build same-origin download URL
    u = urlparse(str(request.base_url))
    origin = f"{u.scheme}://{u.netloc}"
    return {"download_url": f"{origin}/api/download?payload={b64}"}