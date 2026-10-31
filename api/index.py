from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import notes
from api.routers import trades
from api.routers import approvals
from api.routers import journal
from api.routers import revolut_x
from api.routers import recommendations
from api.routers import agent
from api.routers import openai_balance
from api.routers import cron
from api.routers import exits
from api.routers import notifications
from api.routers import advisor
from api.routers import copy_book
from api.routers import helm_strategy
from api.routers import metaapi

app = FastAPI(
    title="AURUM OS API",
    description="Backend for the AI-native gold trading copilot",
    version="1.0.0",
    # Vercel strips trailing slashes (308); FastAPI would 307 back → loop.
    redirect_slashes=False,
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
app.include_router(revolut_x.router, prefix="/api")
app.include_router(recommendations.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(openai_balance.router, prefix="/api")
app.include_router(cron.router, prefix="/api")
app.include_router(exits.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(advisor.router, prefix="/api")
app.include_router(copy_book.router, prefix="/api")
app.include_router(helm_strategy.router, prefix="/api")
app.include_router(metaapi.router, prefix="/api")
