import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  getMe,
  login as loginApi,
  logout as logoutApi,
  register as registerApi,
  setUnauthorizedHandler,
  verifyTwoFactor as verifyTwoFactorApi,
} from "../services/api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  // Bumped by every call below that can set `user`. Each call captures its
  // own id and only commits its result if it's still the most recently
  // issued one -- otherwise it's a stale response and gets discarded. This
  // is what stops the mount-triggered getMe() (which can easily take
  // longer than a login the user submits right after the page loads) from
  // resolving *after* that fresh login and overwriting it back to null.
  const requestIdRef = useRef(0);

  const refresh = useCallback(() => {
    const id = ++requestIdRef.current;
    return getMe()
      .then((u) => {
        if (requestIdRef.current === id) setUser(u);
      })
      .catch(() => {
        if (requestIdRef.current === id) setUser(null);
      })
      .finally(() => {
        // Same staleness guard as setUser above, deliberately -- not
        // unconditional. `loading` must flip in lockstep with whichever
        // request actually wins and commits `user`, not with "some
        // request settled". React's dev-mode double-invoked effects fire
        // this twice on one mount; if the guard were removed, the STALE
        // one settling first would flip loading to false while the
        // winning one (which sets the real `user`) is still in flight,
        // and ProtectedRoute would see loading=false + user=null in that
        // gap and redirect to /login before the real result ever lands.
        // login()/register() below carry the matching setLoading(false)
        // for the case where *they* are the ones that win the race.
        if (requestIdRef.current === id) setLoading(false);
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      requestIdRef.current += 1;
      setUser(null);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  async function login(email, password) {
    const id = ++requestIdRef.current;
    const result = await loginApi(email, password);
    // A 2FA-enabled account gets a pending_token, not a session -- there's
    // no user to commit yet, the caller (Login page) still owes a second
    // step (verifyTwoFactor below) before this resolves into a real
    // signed-in state.
    if (result.requires_2fa) {
      return result;
    }
    // Also clears `loading`, not just `user` -- login/register can win the
    // race against the mount-triggered refresh() above, and whichever one
    // wins has to be the one that ends the loading phase.
    if (requestIdRef.current === id) {
      setUser(result.user);
      setLoading(false);
    }
    return result;
  }

  async function verifyTwoFactor(pendingToken, code) {
    const id = ++requestIdRef.current;
    const nextUser = await verifyTwoFactorApi(pendingToken, code);
    if (requestIdRef.current === id) {
      setUser(nextUser);
      setLoading(false);
    }
    return nextUser;
  }

  async function register(email, password) {
    const id = ++requestIdRef.current;
    const nextUser = await registerApi(email, password);
    if (requestIdRef.current === id) {
      setUser(nextUser);
      setLoading(false);
    }
    return nextUser;
  }

  async function logout() {
    const id = ++requestIdRef.current;
    await logoutApi().catch(() => {});
    if (requestIdRef.current === id) setUser(null);
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, login, register, logout, refresh, verifyTwoFactor }}
    >
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
