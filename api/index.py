import base64, hashlib, io, json, re, tempfile, os
from typing import List, Literal, Optional
from fastapi import FastAPI, Response, HTTPException, Request
from pydantic import BaseModel, Field, validator

app = FastAPI(title="Anki Deck Packager")

# ---------- Models ----------
NoteType = Literal["Basic", "Basic (and reverse)", "Cloze"]

class Card(BaseModel):
  note_type: NoteType
  front: Optional[str] = None   # Basic/Reverse
  back: Optional[str] = None    # Basic/Reverse
  text: Optional[str] = None    # Cloze
  tags: Optional[List[str]] = None

  @validator("front", always=False)
  def front_required_for_basic(cls, v, values):
    if values.get("note_type") in ["Basic", "Basic (and reverse)"] and not v:
      raise ValueError("front required for Basic/Reverse")
    return v

  @validator("back", always=False)
  def back_required_for_basic(cls, v, values):
    if values.get("note_type") in ["Basic", "Basic (and reverse)"] and not v:
      raise ValueError("back required for Basic/Reverse")
    return v

  @validator("text", always=False)
  def text_required_for_cloze(cls, v, values):
    if values.get("note_type") == "Cloze" and not v:
      raise ValueError("text required for Cloze")
    # enforce <= 2 clozes
    if v:
      n = len(re.findall(r"{{c\d+::", v))
      if n > 2:
        raise ValueError(f"Cloze has {n} deletions; max is 2")
    return v

class BuildRequest(BaseModel):
  deck_name: Optional[str] = Field(default="Learning AI")
  tags_default: Optional[List[str]] = None
  cards: List[Card]

def kebab(s: str) -> str:
  # normalize tags to kebab-case ASCII
  s = s.lower()
  s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
  return s

def normalize_tags(tags: Optional[List[str]]) -> List[str]:
  out = []
  for t in tags or []:
    # preserve 'source:' / 'topic:' prefix if present, but kebab-case the value
    if ":" in t:
      k, v = t.split(":", 1)
      out.append(f"{k}:{kebab(v)}")
    else:
      out.append(kebab(t))
  return out

# ---------- Build helpers ----------
def build_apkg(deck_name: str, cards: List[Card]) -> bytes:
  import genanki
  deck_id = int(hashlib.sha256(deck_name.encode("utf-8")).hexdigest()[:12], 16)

  BASIC_MODEL_ID = 1607392319
  CLOZE_MODEL_ID = 998877665
  REVERSE_NAME = "Basic (and reverse)"

  basic_model = genanki.Model(
    BASIC_MODEL_ID, "Basic",
    fields=[{"name": "Front"}, {"name": "Back"}],
    templates=[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=\"answer\">{{Back}}"}],
    css=".card { font-family: arial; font-size: 16px; text-align: left; }",
  )

  reverse_model = genanki.Model(
    BASIC_MODEL_ID + 1, REVERSE_NAME,
    fields=[{"name": "Front"}, {"name": "Back"}],
    templates=[
      {"name": "Forward", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=\"answer\">{{Back}}"},
      {"name": "Reverse", "qfmt": "{{Back}}",  "afmt": "{{Back}}<hr id=\"answer\">{{Front}}"}
    ],
    css=".card { font-family: arial; font-size: 16px; text-align: left; }",
  )

  cloze_model = genanki.Model(
    CLOZE_MODEL_ID, "Cloze",
    fields=[{"name": "Text"}],
    templates=[{"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}"}],
    css=".card { font-family: arial; font-size: 16px; text-align: left; }",
    model_type=genanki.Model.CLOZE,
  )

  deck = genanki.Deck(deck_id, deck_name)

  for c in cards:
    t = normalize_tags(c.tags)
    if c.note_type == "Basic":
      note = genanki.Note(model=basic_model, fields=[c.front, c.back], tags=t)
    elif c.note_type == "Basic (and reverse)":
      note = genanki.Note(model=reverse_model, fields=[c.front, c.back], tags=t)
    else:
      note = genanki.Note(model=cloze_model, fields=[c.text], tags=t)
    deck.add_note(note)

  # Write to a temp file in /tmp (writeable on Vercel)
  tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".apkg", dir="/tmp")
  tmp.close()
  try:
    genanki.Package(deck).write_to_file(tmp.name)
    with open(tmp.name, "rb") as f:
      return f.read()
  finally:
    try: os.remove(tmp.name)
    except OSError: pass

def build_download_link(base_url: str, payload: dict) -> str:
  # encode small payload in URL for a stateless GET -> file download
  raw = json.dumps(payload).encode("utf-8")
  b64 = base64.urlsafe_b64encode(raw).decode("ascii")
  return f"{base_url.rstrip('/')}/download?payload={b64}"

# ---------- Routes ----------
@app.get("/")
def health():
  return {"ok": True, "service": "anki-packager"}

@app.post("/build-apkg")
def build_apkg_post(req: BuildRequest, request: Request):
  payload = {
    "deck_name": req.deck_name or "Learning AI",
    "cards": [c.model_dump() for c in req.cards]
  }
  import base64, json
  b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
  base = str(request.base_url).rstrip("/")
  return {"download_url": f"{base}/download?payload={b64}"}

@app.get("/download")
def download(payload: str):
  try:
    data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
  except Exception:
    raise HTTPException(status_code=400, detail="Bad payload")

  deck_name = data.get("deck_name") or "Learning AI"
  cards = [Card(**c) for c in data.get("cards", [])]
  if not cards:
    raise HTTPException(status_code=400, detail="No cards")

  content = build_apkg(deck_name, cards)
  filename = re.sub(r"[^a-zA-Z0-9._-]+", "_", f"{deck_name}.apkg") or "deck.apkg"
  return Response(
    content=content,
    media_type="application/octet-stream",
    headers={"Content-Disposition": f'attachment; filename="{filename}"'}
  )
