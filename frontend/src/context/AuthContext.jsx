import { useState, useCallback, useEffect } from "react";
import { getStoredAuth, setStoredAuth, decodeJwtPayload, UNAUTHORIZED_EVENT } from "../lib/api";
import { AuthContext } from "./auth-context";

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => getStoredAuth());
  // 저장된 토큰을 복원한 것과 이번 화면에서 새로 로그인한 것을 구분한다.
  // 퀵스타트는 성공한 로그인 직후마다 띄우되, 새로고침에서는 반복하지 않는다.
  const [loginSequence, setLoginSequence] = useState(0);

  const login = useCallback((data) => {
    setStoredAuth(data);
    setAuth(data);
    setLoginSequence((sequence) => sequence + 1);
  }, []);

  const logout = useCallback(() => {
    setStoredAuth(null);
    setAuth(null);
  }, []);

  // 어느 화면에서든 401/403이 오면 apiFetchJson이 이 이벤트를 쏜다. 여기서 한 번만
  // 로그아웃 상태로 바꾸면 RequireRole이 로그인 화면으로 보낸다 —
  // 페이지마다 401 처리를 따로 쓰지 않아도 된다.
  useEffect(() => {
    const onUnauthorized = () => setAuth(null);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated: !!auth?.token,
        role: auth?.role ?? null,
        verificationType: auth?.verificationType ?? null,
        username: auth?.token ? decodeJwtPayload(auth.token)?.username ?? null : null,
        loginSequence,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
