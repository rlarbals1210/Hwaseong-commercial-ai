import { useState, useCallback, useEffect } from "react";
import { getStoredAuth, setStoredAuth, decodeJwtPayload, UNAUTHORIZED_EVENT } from "../lib/api";
import { AuthContext } from "./auth-context";

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => getStoredAuth());

  const login = useCallback((data) => {
    setStoredAuth(data);
    setAuth(data);
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
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
