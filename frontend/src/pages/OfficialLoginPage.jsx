import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../lib/api";
import { useAuth } from "../context/auth-context";

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

  return (
    <div
      style={{
        minHeight: "calc(100vh - 152px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 16px",
        borderRadius: 24,
        background: "linear-gradient(135deg, var(--primary) 0%, var(--primary-container) 100%)",
      }}
    >
      <div style={{ width: "100%", maxWidth: 400 }}>
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <span
            style={{
              display: "inline-block",
              background: "var(--surface-container-lowest)",
              color: "var(--primary)",
              fontWeight: 700,
              fontSize: 14,
              padding: "8px 16px",
              borderRadius: 8,
              marginBottom: 16,
            }}
          >
            Reverse Nodaji
          </span>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#fff", margin: "0 0 4px" }}>
            화성시 소상공인 AI 정책지원 플랫폼
          </h1>
          <p style={{ fontSize: 13, color: "rgba(255,255,255,0.7)", margin: 0 }}>공무원 · 공식 행정 시스템 로그인</p>
        </div>

        <form
          onSubmit={submit}
          style={{
            background: "var(--surface-container-lowest)",
            border: "1px solid var(--border-subtle)",
            borderRadius: 12,
            padding: 32,
          }}
        >
          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 14, fontWeight: 600, color: "var(--on-surface)", display: "block", marginBottom: 8 }}>
              아이디 (ID)
            </label>
            <div style={{ position: "relative" }}>
              <span
                className="material-symbols-outlined"
                style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--on-surface-variant)", fontSize: 20 }}
              >
                person
              </span>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="관리자 아이디를 입력하세요"
                style={{
                  width: "100%",
                  padding: "12px 12px 12px 40px",
                  borderRadius: 8,
                  border: "1px solid var(--border-subtle)",
                  fontSize: 14,
                  boxSizing: "border-box",
                }}
              />
            </div>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ fontSize: 14, fontWeight: 600, color: "var(--on-surface)", display: "block", marginBottom: 8 }}>
              비밀번호 (Password)
            </label>
            <div style={{ position: "relative" }}>
              <span
                className="material-symbols-outlined"
                style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--on-surface-variant)", fontSize: 20 }}
              >
                lock
              </span>
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="비밀번호를 입력하세요"
                style={{
                  width: "100%",
                  padding: "12px 40px 12px 40px",
                  borderRadius: 8,
                  border: "1px solid var(--border-subtle)",
                  fontSize: 14,
                  boxSizing: "border-box",
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                style={{
                  position: "absolute",
                  right: 8,
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--on-surface-variant)",
                  display: "flex",
                  padding: 4,
                }}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
                  {showPassword ? "visibility_off" : "visibility"}
                </span>
              </button>
            </div>
          </div>

          {error && <div style={{ fontSize: 13, color: "var(--status-red)", marginBottom: 16 }}>{error}</div>}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "13px 0",
              background: loading ? "var(--secondary-container)" : "var(--secondary)",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 700,
              cursor: loading ? "default" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
            }}
          >
            {loading ? "로그인 중..." : "시스템 로그인"}
            {!loading && (
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                login
              </span>
            )}
          </button>
        </form>

        <p style={{ textAlign: "center", fontSize: 12, color: "rgba(255,255,255,0.6)", marginTop: 24 }}>
          © 2026 Hwaseong City AI Policy Division. All rights reserved.
        </p>
      </div>
    </div>
  );
}
