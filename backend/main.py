import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import alerts, cells, compare, policy, analysis, auth, workflow

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

# 공무원 정책 의사결정 지원 전용 API.
# 시민(소상공인) 직접조회 라우터(consultation)는 2026-08-18 설계 결정으로 제외했다.
app.include_router(auth.router)
app.include_router(alerts.router)
app.include_router(cells.router)
app.include_router(compare.router)
app.include_router(policy.router)
app.include_router(analysis.router)
app.include_router(workflow.router)


@app.get("/")
def root():
    return {"status": "ok", "project": "화성시 소상공인 AI 정책지원 플랫폼"}
