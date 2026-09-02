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
      {/* 마크만 있으면 이 화면이 어느 트랙인지 이름으로 확인할 방법이 없다.
          공무원 사이드바와 같은 2단 구성 — 위는 우산 이름, 아래는 이 트랙의 이름. */}
      <Link to="/" aria-label="서비스 소개로 이동" style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--on-surface)", textDecoration: "none" }}>
        <span style={{ width: 32, height: 32, borderRadius: "var(--radius-md)", background: "var(--primary)", color: "white", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700, flexShrink: 0 }}>HS</span>
        <span style={{ display: "flex", flexDirection: "column", lineHeight: 1.3, minWidth: 0 }}>
          <strong style={{ fontSize: 14, fontWeight: 700 }}>화성시 상권 지원</strong>
          <span className="t-caption" style={{ color: "var(--ink-muted)" }}>소상공인 상권 추천 서비스</span>
        </span>
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
