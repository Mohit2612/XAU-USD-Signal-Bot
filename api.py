from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import json
import os
import subprocess
import sys
import threading
import time

app = FastAPI(title="XAUUSD Signal Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start the bot process in the background
bot_process = None

@app.on_event("startup")
def startup_event():
    global bot_process
    print("Starting bot.py in background...")
    # Use the same python executable that is running the API
    bot_process = subprocess.Popen(
        [sys.executable, "-u", "bot.py"],
        env=dict(os.environ, PYTHONIOENCODING="utf-8")
    )

@app.on_event("shutdown")
def shutdown_event():
    global bot_process
    if bot_process:
        print("Shutting down bot.py...")
        bot_process.terminate()

@app.get("/api/state")
def get_state():
    try:
        if os.path.exists("state.json"):
            with open("state.json", "r") as f:
                return json.load(f)
        return {"status": "Waiting for bot to generate state..."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/trades")
def get_trades():
    try:
        if os.path.exists("trade_journal.json"):
            with open("trade_journal.json", "r") as f:
                return json.load(f)
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount React App if built
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.exists(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    def serve_react(full_path: str):
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    # If run locally, default to 8000, if on Heroku/Railway, use PORT env var
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
