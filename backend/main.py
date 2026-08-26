import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import (
    alerts, cells, compare, policy, analysis, auth, workflow, public, recommend, trends, report,
)

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

# 공개 라우터 — 인증 가드 없음.
#   public.py    관측치 기반 조회(둘러보기·지도·업종 계층)
#   recommend.py 예측 기반 추천. 2026-08-26 결정으로 공개 범위에 들어왔다 —
#                조건 넷(셀 단위 등급만/지도는 관측치로/표본부족 등급 미부여/면책 문구)은
#                각 파일 맨 위에 적어 뒀다.
app.include_router(public.router)
app.include_router(recommend.router)
app.include_router(trends.router)
app.include_router(report.router)


@app.get("/")
def root():
    return {"status": "ok", "project": "화성시 소상공인 AI 정책지원 플랫폼"}
