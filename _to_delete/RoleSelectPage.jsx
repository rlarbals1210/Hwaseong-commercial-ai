import { useNavigate } from "react-router-dom";

const ROLES = [
  {
    key: "official",
    label: "공무원",
    icon: "admin_panel_settings",
    color: "var(--primary)",
    iconBg: "var(--primary)",
    desc: "AI 폐업위험 조기경보와 정책자금 우선순위 매트릭스를 관리하고 공식 정책 결정을 지원합니다.",
    bullets: [
      { icon: "dashboard", label: "조기경보 대시보드" },
      { icon: "map", label: "공실위험 지도" },
      { icon: "grid_view", label: "정책자금 우선순위 매트릭스" },
    ],
    cta: "공무원 로그인",
    path: "/login/official",
  },
  {
    key: "citizen",
    label: "시민 (소상공인)",
    icon: "storefront",
    color: "var(--secondary)",
    iconBg: "var(--secondary)",
    desc: "사업자등록번호만으로 예비창업자를 위한 AI 창업 생존확률 상담을 바로 조회하세요.",
    bullets: [{ icon: "chat_bubble", label: "창업 상담 조회" }],
    cta: "시민 로그인",
    path: "/login/citizen",
  },
];

export default function RoleSelectPage() {
  const navigate = useNavigate();

  return (
    <div style={{ minHeight: "calc(100vh - 56px)", display: "flex", alignItems: "center", justifyContent: "center", padding: "48px 0" }}>
      <div style={{ maxWidth: 880, width: "100%", padding: "0 16px" }}>
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <h1 style={{ fontSize: 32, fontWeight: 700, color: "var(--primary)", margin: "0 0 12px", letterSpacing: "-0.01em" }}>
            화성시 소상공인 AI 정책지원 플랫폼
          </h1>
          <p style={{ fontSize: 16, color: "var(--on-surface-variant)", lineHeight: 1.6, margin: 0 }}>
            사용자 유형에 맞는 서비스로 입장해 주세요.
            <br />
            소상공인 폐업 위험 조기경보와 정책자금 우선순위를 지원하는 AI 플랫폼입니다.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
          {ROLES.map((r) => (
            <button
              key={r.key}
              className="role-card"
              onClick={() => navigate(r.path)}
              style={{
                background: "var(--surface-container-lowest)",
                border: "1px solid var(--border-subtle)",
                borderRadius: 16,
                padding: 32,
                cursor: "pointer",
                textAlign: "left",
                display: "flex",
                flexDirection: "column",
                gap: 20,
              }}
            >
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: 8,
                  background: r.iconBg,
                  color: "var(--on-primary)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 28 }}>
                  {r.icon}
                </span>
              </div>

              <div>
                <div style={{ fontSize: 20, fontWeight: 600, color: r.color, marginBottom: 8 }}>{r.label}</div>
                <p style={{ fontSize: 15, color: "var(--on-surface-variant)", lineHeight: 1.6, margin: 0 }}>{r.desc}</p>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 12, marginTop: "auto" }}>
                {r.bullets.map((b) => (
                  <div key={b.label} style={{ display: "flex", alignItems: "center", gap: 12, color: "var(--on-surface-variant)" }}>
                    <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
                      {b.icon}
                    </span>
                    <span style={{ fontSize: 14, fontWeight: 600 }}>{b.label}</span>
                  </div>
                ))}
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", color: r.color, fontWeight: 700, marginTop: 8 }}>
                <span style={{ fontSize: 14 }}>{r.cta}</span>
                <span className="material-symbols-outlined role-card-arrow" style={{ fontSize: 20 }}>
                  arrow_forward
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
