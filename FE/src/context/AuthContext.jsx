import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { getAuthToken, onUnauthorized, setAuthToken } from "../api/client";
import { authApi } from "../api/services";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getAuthToken()));

  const logout = useCallback(() => {
    setAuthToken(null);
    setUser(null);
  }, []);

  const refresh = useCallback(async () => {
    if (!getAuthToken()) {
      setLoading(false);
      return;
    }
    try {
      setUser(await authApi.me());
    } catch {
      logout();
    } finally {
      setLoading(false);
    }
  }, [logout]);

  useEffect(() => {
    onUnauthorized(logout);
    refresh();
  }, [logout, refresh]);

  const completeAuth = useCallback(async (tokenResponse) => {
    setAuthToken(tokenResponse.access_token);
    setUser(await authApi.me());
  }, []);

  const login = useCallback(
    async (email, password) => completeAuth(await authApi.login(email, password)),
    [completeAuth],
  );
  const register = useCallback(async (payload) => completeAuth(await authApi.register(payload)), [completeAuth]);

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      register,
      logout,
      refresh,
      setUser,
      can: (permission) => Boolean(user?.permissions?.includes(permission)),
    }),
    [user, loading, login, register, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
