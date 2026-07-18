import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch } from "../lib/api";
import { useAuth } from "../context/AuthContext";

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
    <div style={{ maxWidth: 380, margin: "60px auto" }}>
      <h1 style={{ fontSize: 20, fontWeight: 800, color: "#111827", margin: "0 0 8px" }}>시민(사업자) 로그인</h1>
      <p style={{ fontSize: 13, color: "#6B7280", marginBottom: 24 }}>
        회원가입 없이 사업자등록번호로 바로 이용할 수 있습니다.
      </p>

      <form onSubmit={submit} style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 12, padding: 24 }}>
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 13, fontWeight: 600, color: "#374151", display: "block", marginBottom: 6 }}>사업자등록번호</label>
          <input
            value={businessNumber}
            onChange={(e) => setBusinessNumber(e.target.value)}
            placeholder="123-45-67890"
            style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1px solid #D1D5DB", fontSize: 14, boxSizing: "border-box" }}
          />
        </div>
        <div style={{ fontSize: 12, color: "#9CA3AF", marginBottom: 20, lineHeight: 1.5 }}>
          형식 확인 전용이며, 실제 사업자 정보와 대조하지 않습니다.
        </div>
        {error && <div style={{ fontSize: 13, color: "#EF4444", marginBottom: 12 }}>{error}</div>}
        <button
          type="submit"
          disabled={loading}
          style={{
            width: "100%", padding: "11px 0", background: loading ? "#6EE7B7" : "#10B981",
            color: "#fff", border: "none", borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: loading ? "default" : "pointer",
          }}
        >
          {loading ? "확인 중..." : "시작하기"}
        </button>
      </form>
    </div>
  );
}
