import { Link, useLocation } from "react-router-dom";

const LINKS = [
  { to: "/browse", label: "상권 둘러보기" },
  { to: "/trends", label: "상권 트렌드" },
  { to: "/report", label: "요약 보고서" },
];

export default function PublicNav() {
  const { pathname } = useLocation();
  return (
    <nav aria-label="공개 상권 메뉴" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, marginBottom: 32 }}>
      <Link to="/" aria-label="서비스 소개로 이동" style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--on-surface)", textDecoration: "none" }}>
        <span style={{ width: 32, height: 32, borderRadius: "var(--radius-md)", background: "var(--primary)", color: "white", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700 }}>RN</span>
      </Link>
      <div style={{ display: "flex", gap: 4, flexWrap: "wrap", justifyContent: "flex-end" }}>
        {LINKS.map((link) => {
          const active = pathname === link.to;
          return (
            <Link
              key={link.to}
              to={link.to}
              className="t-caption"
              style={{
                color: active ? "var(--primary)" : "var(--ink-muted)",
                background: active ? "var(--primary-fixed)" : "transparent",
                borderRadius: "var(--radius-full)",
                padding: "7px 11px",
                textDecoration: "none",
                fontWeight: active ? 600 : 400,
              }}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
