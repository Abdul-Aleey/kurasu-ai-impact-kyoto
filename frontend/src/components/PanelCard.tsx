import type { AgentSummary } from "../types";

interface Props {
  agent: AgentSummary;
  onClick: () => void;
}

export function PanelCard({ agent, onClick }: Props) {
  return (
    <button
      onClick={onClick}
      className="group flex aspect-square w-full flex-col items-center justify-center gap-2
                 rounded-2xl border border-white/10 bg-white/5 p-4 text-center shadow-lg
                 backdrop-blur-sm transition hover:border-fuchsia-400/40 hover:bg-white/10
                 active:scale-[0.97]"
    >
      <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl
                       bg-gradient-to-br from-fuchsia-500/30 to-indigo-500/30 text-3xl">
        {agent.icon}
      </div>
      <div className="text-base font-semibold leading-tight text-white">{agent.title}</div>
      <div className="line-clamp-2 text-xs leading-snug text-white/60">{agent.subtitle}</div>
    </button>
  );
}
