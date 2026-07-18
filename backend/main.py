import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .routers import alerts, policy, analysis, consultation, auth

Base.metadata.create_all(bind=engine)

app = FastAPI(title="화성시 소상공인 AI 정책지원 플랫폼", version="1.0.0")

_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5174,http://localhost:5173,http://localhost:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(alerts.router)
app.include_router(policy.router)
app.include_router(analysis.router)
app.include_router(consultation.router)


@app.get("/")
def root():
    return {"status": "ok", "project": "화성시 소상공인 AI 정책지원 플랫폼"}
