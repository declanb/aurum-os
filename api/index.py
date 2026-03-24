from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import notes
from api.routers import trades
from api.routers import approvals
from api.routers import journal
from api.routers import vantage

app = FastAPI(
    title="AURUM OS API",
    description="Backend for the AI-native gold trading copilot",
    version="1.0.0"
)

# Standard permissive CORS for local dev. Tighten in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "AURUM OS API is running.", "status": "ok"}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "aurum-os-api"}

app.include_router(notes.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
app.include_router(approvals.router, prefix="/api")
app.include_router(journal.router, prefix="/api")
app.include_router(vantage.router, prefix="/api")
