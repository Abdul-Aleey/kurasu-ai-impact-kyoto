import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getAgents, getConfig, getHealth } from "../api/client";
import type { AgentSummary, HealthResponse } from "../types";

interface AppDataValue {
  agents: AgentSummary[] | null;
  agentsError: string | null;
  backendReady: boolean;
  health: HealthResponse | null;
  refreshHealth: () => void;
}

const AppDataContext = createContext<AppDataValue>({
  agents: null,
  agentsError: null,
  backendReady: true,
  health: null,
  refreshHealth: () => {},
});

/** Fetches config/agents once per app load (they rarely change), not once
 * per Home screen visit -- this provider sits above the router (like
 * LocationProvider) so navigating back to Home reads already-fetched data
 * instead of re-flashing the loading skeletons every time.
 *
 * Health is different: it's a live status indicator, so it re-checks on
 * every call to `refreshHealth` (Home calls this on each visit) rather than
 * only once -- otherwise a slow or momentarily-failed first check (e.g. a
 * Cloud Run cold start) would leave the badge stuck on "Checking model..."
 * forever, with no way to prompt a retry short of a full page reload. It
 * never resets to null before re-checking, though, so the previous known
 * status stays visible (no flicker) until the new one resolves. */
export function AppDataProvider({ children }: { children: React.ReactNode }) {
  const [agents, setAgents] = useState<AgentSummary[] | null>(null);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  const [backendReady, setBackendReady] = useState(true);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  const refreshHealth = useCallback(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth({ modelConnected: false, detail: "Couldn't reach the backend." }));
  }, []);

  useEffect(() => {
    getConfig()
      .then((c) => setBackendReady(c.backendReady))
      .catch(() => setBackendReady(true)); // don't block UI on a /config hiccup

    getAgents()
      .then(setAgents)
      .catch((e) => setAgentsError(e.message));

    refreshHealth();
  }, [refreshHealth]);

  return (
    <AppDataContext.Provider value={{ agents, agentsError, backendReady, health, refreshHealth }}>
      {children}
    </AppDataContext.Provider>
  );
}

export function useAppData(): AppDataValue {
  return useContext(AppDataContext);
}
