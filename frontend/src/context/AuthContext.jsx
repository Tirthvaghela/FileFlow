import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  getMe,
  login as loginApi,
  logout as logoutApi,
  register as registerApi,
} from "../services/api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    return getMe()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function login(email, password) {
    const nextUser = await loginApi(email, password);
    setUser(nextUser);
    return nextUser;
  }

  async function register(email, password) {
    const nextUser = await registerApi(email, password);
    setUser(nextUser);
    return nextUser;
  }

  async function logout() {
    await logoutApi().catch(() => {});
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
