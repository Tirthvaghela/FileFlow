import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getRules, updateRules as updateRulesApi } from "../services/api.js";

const RulesContext = createContext(null);

// Sidebar, Dashboard, Rules and Settings all read/write the same rules.json.
// A single provider avoids four independent fetches going stale relative to
// each other -- toggling automation in the sidebar now updates every screen
// that shows it, instead of only the component that made the change.
export function RulesProvider({ children }) {
  const [rules, setRules] = useState(null);

  const refresh = useCallback(() => {
    return getRules()
      .then(setRules)
      .catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const saveRules = useCallback(
    async (next) => {
      const previous = rules;
      setRules(next);
      try {
        const saved = await updateRulesApi(next);
        setRules(saved);
        return saved;
      } catch (err) {
        setRules(previous);
        throw err;
      }
    },
    [rules],
  );

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
