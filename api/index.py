# api/index.py
from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def health_root():
    return {"ok": True, "service": "anki-packager"}

# Some users accidentally hit /api/index or add a trailing slash.
@app.get("/index")
def health_index():
    return {"ok": True, "service": "anki-packager"}

# Catch-all to show what path the app is seeing (for debugging).
@app.api_route("/{path:path}", methods=["GET","POST","HEAD","OPTIONS"])
def catch_all(path: str):
    return {"detail": "Not Found at FastAPI app", "saw_path": f"/{path}"}