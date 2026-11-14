import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type Me } from "../api/client";

interface AuthValue {
  me: Me | null;
  loading: boolean;
  login: (loginId: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (loginId: string, password: string) => {
    const user = await api.login(loginId, password);
    setMe(user);
    return user;
  }, []);

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined);
    setMe(await api.me().catch(() => null));
  }, []);

  const value = useMemo(() => ({ me, loading, login, logout }), [me, loading, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export const isSignedIn = (me: Me | null) => !!me && me.role !== "public";
