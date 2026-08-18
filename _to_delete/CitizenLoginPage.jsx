import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../lib/api";
import { useAuth } from "../context/AuthContext";

function formatBusinessNumber(raw) {
  const digits = raw.replace(/\D/g, "").slice(0, 10);
  if (digits.length <= 3) return digits;
  if (digits.length <= 5) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
}

const FEATURES = [
  {
    icon: "search_check",
    label: "간편 조회",
    desc: "회원가입 없이 사업자등록번호만으로 바로 이용할 수 있습니다.",
  },
  {
    icon: "lock",
    label: "개인정보 미저장",
    desc: "입력한 사업자등록번호는 형식 확인에만 사용되고 별도로 저장되지 않습니다.",
  },
];

export default function CitizenLoginPage() {
  const [businessNumber, setBusinessNumber] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const r = await apiFetch("/api/auth/citizen/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ business_number: businessNumber }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail || "로그인에 실패했습니다.");
      login({ token: data.access_token, role: data.role, verificationType: data.verification_type });
      navigate("/consult");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: "48px 0" }}>
      <div
        style={{
          maxWidth: 1000,
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "1.1fr 1fr",
          gap: 48,
          alignItems: "center",
        }}
      >
        <div>
          <h1 style={{ fontSize: 40, fontWeight: 700, color: "var(--primary)", lineHeight: 1.25, margin: "0 0 16px", letterSpacing: "-0.02em" }}>
            반가워요,
            <br />
            사장님!
          </h1>
          <p style={{ fontSize: 18, color: "var(--on-surface-variant)", lineHeight: 1.6, margin: "0 0 24px", maxWidth: 440 }}>
            복잡한 회원가입 없이 사업자등록번호 하나로 AI 창업 상담을 즉시 확인하세요.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {FEATURES.map((f) => (
              <div
                key={f.label}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 16,
                  padding: 16,
                  background: "var(--surface-container-lowest)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: 12,
                }}
              >
                <div
                  style={{
                    width: 36,
                    height: 36,
                    flexShrink: 0,
                    borderRadius: 8,
                    background: "var(--surface-container-low)",
                    color: "var(--secondary)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <span className="material-symbols-outlined" style={{ fontSize: 20 }}>
                    {f.icon}
                  </span>
                </div>
                <div>
                  <p style={{ fontSize: 14, fontWeight: 600, color: "var(--on-surface)", margin: "0 0 4px" }}>{f.label}</p>
                  <p style={{ fontSize: 13, color: "var(--on-surface-variant)", margin: 0, lineHeight: 1.5 }}>{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <form
          onSubmit={submit}
          style={{
            background: "var(--surface-container-lowest)",
            border: "1px solid var(--border-subtle)",
            borderRadius: 16,
            padding: 32,
            display: "flex",
            flexDirection: "column",
            gap: 20,
          }}
        >
          <div>
            <label style={{ fontSize: 14, fontWeight: 600, color: "var(--on-surface-variant)", display: "block", marginBottom: 8 }}>
              사업자 등록번호
            </label>
            <div style={{ position: "relative" }}>
              <input
                value={businessNumber}
                onChange={(e) => setBusinessNumber(formatBusinessNumber(e.target.value))}
                placeholder="000-00-00000"
                style={{
                  width: "100%",
                  height: 52,
                  padding: "0 44px 0 16px",
                  borderRadius: 8,
                  border: "1px solid var(--border-subtle)",
                  fontSize: 18,
                  boxSizing: "border-box",
                }}
              />
              <span
                className="material-symbols-outlined"
                style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", color: "var(--on-surface-variant)", fontSize: 20 }}
              >
                business
              </span>
            </div>
            <p style={{ fontSize: 12, color: "var(--on-surface-variant)", margin: "8px 0 0" }}>
              숫자 10자리만 입력해 주세요. 형식 확인 전용이며, 실제 사업자 정보와 대조하지 않습니다.
            </p>
          </div>

          {error && <div style={{ fontSize: 13, color: "var(--status-red)" }}>{error}</div>}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              height: 52,
              background: loading ? "var(--secondary-container)" : "var(--secondary)",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              fontSize: 15,
              fontWeight: 700,
              cursor: loading ? "default" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
            }}
          >
            {loading ? "확인 중..." : "창업 상담 조회하기"}
            {!loading && (
              <span className="material-symbols-outlined" style={{ fontSize: 18 }}>
                arrow_forward
              </span>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
