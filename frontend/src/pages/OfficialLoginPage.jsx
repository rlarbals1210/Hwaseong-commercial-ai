import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../lib/api";
import { useAuth } from "../context/auth-context";

// 로그인은 페이지 셸(사이드바·상단바) 밖에서 렌더되므로 자체 전체화면 레이아웃을 갖는다.
// 그라디언트 대신 웜 캔버스 위에 흰 카드 하나 — "겹친 종이" 원칙을 진입 화면에서도 유지한다.
function Field({ label, icon, children, hint }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <label className="t-caption" style={{ display: "block", fontWeight: 600, color: "var(--ink-secondary)", marginBottom: 7 }}>
        {label}
      </label>
      <div style={{ position: "relative" }}>
        <span
          className="material-symbols-outlined"
          style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--ink-faint)", fontSize: 20, pointerEvents: "none" }}
        >
          {icon}
        </span>
        {children}
      </div>
      {hint && <div className="t-caption" style={{ color: "var(--ink-faint)", marginTop: 6 }}>{hint}</div>}
    </div>
  );
}

export default function OfficialLoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const r = await apiFetch("/api/auth/official/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "로그인에 실패했습니다.");
      login({ token: data.access_token, role: data.role, verificationType: data.verification_type });
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const inputStyle = { width: "100%", padding: "11px 12px 11px 40px", boxSizing: "border-box" };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 16px",
        background: "var(--surface-gray)",
      }}
    >
      <div style={{ width: "100%", maxWidth: 400 }}>
        {/* 브랜드 */}
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: "var(--radius-lg)",
              background: "var(--primary)",
              color: "var(--on-primary)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 700,
              fontSize: 19,
              letterSpacing: "-0.5px",
              marginBottom: 16,
            }}
          >
            RN
          </div>
          <h1 className="t-h2" style={{ margin: 0 }}>리버스 노다지</h1>
          <p className="t-body-sm" style={{ color: "var(--ink-muted)", margin: "6px 0 0" }}>
            화성시 소상공인 폐업위험 조기경보
          </p>
        </div>

        {/* 로그인 카드 */}
        <form onSubmit={submit} className="card" style={{ padding: 28 }}>
          <div style={{ marginBottom: 22 }}>
            <h2 className="t-title" style={{ margin: 0 }}>공무원 로그인</h2>
            <p className="t-caption" style={{ color: "var(--ink-muted)", margin: "4px 0 0" }}>
              담당 부서 계정으로 접속하세요.
            </p>
          </div>

          <Field label="아이디" icon="person">
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="관리자 아이디"
              autoComplete="username"
              style={inputStyle}
            />
          </Field>

          <Field label="비밀번호" icon="lock">
            <input
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="비밀번호"
              autoComplete="current-password"
              style={{ ...inputStyle, paddingRight: 40 }}
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 표시"}
              style={{
                position: "absolute",
                right: 8,
                top: "50%",
                transform: "translateY(-50%)",
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "var(--ink-muted)",
                display: "flex",
                padding: 4,
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
                {showPassword ? "visibility_off" : "visibility"}
              </span>
            </button>
          </Field>

          {error && (
            <div
              className="t-caption"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                color: "var(--error)",
                background: "var(--error-soft)",
                padding: "10px 12px",
                borderRadius: "var(--radius-md)",
                marginBottom: 16,
              }}
            >
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>error</span>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn-primary"
            disabled={loading}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              opacity: loading ? 0.7 : 1,
              cursor: loading ? "default" : "pointer",
            }}
          >
            {loading && (
              <span className="material-symbols-outlined spin" style={{ fontSize: 18 }}>progress_activity</span>
            )}
            {loading ? "로그인 중" : "로그인"}
          </button>
        </form>

        <p className="t-caption" style={{ textAlign: "center", color: "var(--ink-faint)", marginTop: 20, lineHeight: 1.6 }}>
          이 시스템은 화성시 담당 공무원 전용입니다.
          <br />
          계정 문의는 소관 부서에 요청하세요.
        </p>
      </div>
    </div>
  );
}
