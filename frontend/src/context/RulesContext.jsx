import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { getRules, updateRules as updateRulesApi } from "../services/api.js";

const RulesContext = createContext(null);

// Sidebar, Dashboard, Rules and Settings all read/write the same rules.json.
// A single provider avoids four independent fetches going stale relative to
// each other -- toggling automation in the sidebar now updates every screen
// that shows it, instead of only the component that made the change.
export function RulesProvider({ children }) {
  const [rules, setRules] = useState(null);
  // Mirrors `rules` but updates synchronously (no waiting on a re-render),
  // so a save queued right after another always builds on that other
  // save's result instead of a stale snapshot from before either started.
  const latestRulesRef = useRef(null);
  // Chains saves one after another instead of letting them fire
  // concurrently. The whole API is a single full-document PUT, so two
  // overlapping saves (e.g. dragging a Settings slider fires one per
  // pointer-move event, or the sidebar's automation switch flipped while a
  // Rules-page toggle is still in flight) each used to build their payload
  // from the same pre-save `rules`, and whichever response landed last
  // silently overwrote the other's change on the server.
  const queueRef = useRef(Promise.resolve());

  const refresh = useCallback(() => {
    return getRules()
      .then((r) => {
        latestRulesRef.current = r;
        setRules(r);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Accepts either a plain object or an updater `(current) => next`, same
  // shape as React's functional setState -- the updater form is what makes
  // this actually fix lost updates rather than just smoothing out response
  // ordering, since it's resolved against the latest *optimistic* state
  // right when it's called, not a snapshot from this component's last
  // render. The optimistic setRules(next)/ref-advance happens synchronously
  // (not deferred into the queued network call below) so a second save
  // fired immediately after the first -- before either request has
  // resolved -- still builds on top of the first's change instead of
  // stepping on it, and so the UI updates immediately rather than waiting
  // on a round trip.
  const saveRules = useCallback((update) => {
    const base = latestRulesRef.current;
    const next = typeof update === "function" ? update(base) : update;
    latestRulesRef.current = next;
    setRules(next);

    const run = async () => {
      try {
        const saved = await updateRulesApi(next);
        latestRulesRef.current = saved;
        setRules(saved);
        return saved;
      } catch (err) {
        // Only roll back if nothing newer has since landed on top of this
        // save -- otherwise a failure here would wipe out a later, still
        // in-flight save's optimistic UI state along with its own.
        if (latestRulesRef.current === next) {
          latestRulesRef.current = base;
          setRules(base);
        }
        throw err;
      }
    };
    // The optimistic merge above already happened; this queue only
    // serializes the actual network PUTs so they land at the server in the
    // same order they were triggered, each carrying the full (by-then
    // merged) document instead of racing on response order.
    const result = queueRef.current.then(run, run);
    // One save's rejection must not permanently wedge every save queued
    // after it -- each caller still sees its own promise reject normally.
    queueRef.current = result.catch(() => {});
    return result;
  }, []);

  return (
    <RulesContext.Provider value={{ rules, setRules, saveRules, refresh }}>
      {children}
    </RulesContext.Provider>
  );
}

export function useRules() {
  const ctx = useContext(RulesContext);
  if (!ctx) {
    throw new Error("useRules must be used within a RulesProvider");
  }
  return ctx;
}
