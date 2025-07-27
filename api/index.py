from fastapi import FastAPI
app = FastAPI()

# Accept both prefixed and non-prefixed paths
@app.get("/")
@app.get("/index")
@app.get("/api/index")
def health():
    return {"ok": True, "service": "anki-packager"}