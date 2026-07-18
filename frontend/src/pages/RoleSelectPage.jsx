import { useNavigate } from "react-router-dom";

const ROLES = [
  {
    key: "official",
    label: "공무원",
    desc: "조기경보 대시보드 · 공실위험 지도 · 정책자금 우선순위 매트릭스 열람",
    path: "/login/official",
    color: "#2563EB",
    bg: "#EFF6FF",
  },
  {
    key: "citizen",
    label: "시민 (사업자)",
    desc: "사업자등록번호로 바로 창업 상담 조회",
    path: "/login/citizen",
    color: "#10B981",
    bg: "#F0FDF4",
  },
];

export default function RoleSelectPage() {
  const navigate = useNavigate();

  return (
    <div style={{ minHeight: "calc(100vh - 56px)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ maxWidth: 640, width: "100%", padding: "0 16px" }}>
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: "#111827", margin: "0 0 8px" }}>
            화성시 소상공인 AI 정책지원 플랫폼
          </h1>
          <p style={{ fontSize: 14, color: "#6B7280" }}>사용자 유형을 선택해주세요</p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          {ROLES.map((r) => (
            <button
              key={r.key}
              onClick={() => navigate(r.path)}
              style={{
                background: r.bg, border: `1px solid ${r.color}33`, borderRadius: 16,
                padding: "32px 20px", cursor: "pointer", textAlign: "left",
                display: "flex", flexDirection: "column", gap: 8,
              }}
            >
              <span style={{ fontSize: 18, fontWeight: 800, color: r.color }}>{r.label}</span>
              <span style={{ fontSize: 13, color: "#374151", lineHeight: 1.5 }}>{r.desc}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
