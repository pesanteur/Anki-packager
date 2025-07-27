# api/index.py
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def health():
    return {"ok": True, "service": "anki-packager"}