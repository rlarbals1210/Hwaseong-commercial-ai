import { createContext, useContext, useState, useCallback } from "react";
import { getStoredAuth, setStoredAuth, decodeJwtPayload } from "../lib/api";

const AuthContext = createContext(null);

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

export function useAuth() {
  return useContext(AuthContext);
}
