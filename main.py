# main.py (optional) for local testing
import uvicorn
from api.index import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
