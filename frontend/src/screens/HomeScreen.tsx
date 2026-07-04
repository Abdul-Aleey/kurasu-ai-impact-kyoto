import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { PanelCard } from "../components/PanelCard";
import { useAppData } from "../context/AppDataContext";

export function HomeScreen() {
  const navigate = useNavigate();
  const { agents, agentsError: error, backendReady, health, refreshHealth } = useAppData();

  useEffect(() => {
    // Health is a live status, so it's worth re-checking on every visit
    // (the badge shows the last-known value while this resolves, so this
    // never causes a flicker) -- otherwise a slow or momentarily-failed
    // first check (e.g. a cold start) would leave it stuck on "Checking
    // model..." with no way to prompt a retry short of a full page reload.
    refreshHealth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto bg-gradient-to-b from-[#1a1030] via-[#160e28] to-[#0d0a1a] px-5 pb-8 pt-12">
      <header className="mb-10 text-center">
        <div className="mb-2 text-4xl">✨</div>
        <h1 className="text-3xl font-bold text-white">Kurasu AI</h1>
        <p className="mt-1 text-sm text-white/50">Your assistant for living in Japan</p>

        <div
          className="mt-3 inline-flex items-center gap-2 rounded-full border border-white/10
                     bg-white/5 px-3 py-1 text-xs text-white/70"
          title={health?.detail ?? "Checking model connection…"}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              health === null
                ? "animate-pulse bg-white/40"
                : health.modelConnected
                  ? "bg-emerald-400"
                  : "bg-red-500"
            }`}
          />
          {health === null ? "Checking model…" : health.modelConnected ? "Model connected" : "Model unavailable"}
        </div>
      </header>

      {!backendReady && (
        <div className="mb-4 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-200">
          Backend isn't configured with a model provider yet. Set GOOGLE_API_KEY in backend/.env.local
          (local dev) or deploy with Vertex AI enabled.
        </div>
      )}

      {backendReady && health && !health.modelConnected && (
        <div className="mb-4 rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200">
          Model configured but not reachable: {health.detail}
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200">
          Couldn't load agents: {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4">
        {agents === null && !error
          ? Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="aspect-square animate-pulse rounded-2xl bg-white/5" />
            ))
          : agents?.map((agent) => (
              <PanelCard
                key={agent.id}
                agent={agent}
                onClick={() => navigate(`/chat/${agent.id}`, { state: { agent } })}
              />
            ))}
      </div>
    </div>
  );
}
