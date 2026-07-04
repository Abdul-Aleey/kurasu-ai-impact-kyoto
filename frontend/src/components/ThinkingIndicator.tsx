import { useEffect, useState } from "react";

const DEFAULT_FINAL_STAGE_MESSAGE =
  "Still working on it -- this one's taking a bit longer than usual…";

/** Each stage's minimum elapsed time (ms) before it's shown. The last stage
 * is a steady state -- it never advances further or loops back, since
 * cycling back to "Thinking…" after a long wait reads as broken/reset
 * rather than reassuring. */
const EARLY_STAGES: { afterMs: number; text: string }[] = [
  { afterMs: 0, text: "Thinking…" },
  { afterMs: 3000, text: "Looking into it…" },
  { afterMs: 8000, text: "Gathering the details…" },
];

const TICK_MS = 500;

interface Props {
  /** What to settle on once the wait reaches its final, steady-state phrase
   * (per-agent, from AgentSummary.longWaitMessage) -- lets an agent whose
   * slowest step is predictable and specific (e.g. actually generating
   * images) name it honestly, instead of every long wait reading the same
   * generic phrase regardless of what's actually happening. */
  finalStageMessage?: string;
}

/** Shown in place of an empty pending bubble while waiting on the backend.
 * Advances through a few honest status phrases based on real elapsed wait
 * time -- it never claims a specific backend step we can't verify (this is
 * a stateless request/response backend, not a stream, so there's no real
 * progress signal to report except which agent is in flight), and it never
 * loops back to an earlier phrase once time has passed, so a long wait
 * doesn't look like the request silently restarted. */
export function ThinkingIndicator({ finalStageMessage = DEFAULT_FINAL_STAGE_MESSAGE }: Props) {
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    const startedAt = Date.now();
    const id = setInterval(() => setElapsedMs(Date.now() - startedAt), TICK_MS);
    return () => clearInterval(id);
  }, []);

  const stages = [...EARLY_STAGES, { afterMs: 15000, text: finalStageMessage }];
  const stage = [...stages].reverse().find((s) => elapsedMs >= s.afterMs) ?? stages[0];

  return (
    <div className="flex items-center gap-2 text-slate-500">
      <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-slate-200 border-t-fuchsia-500" />
      <span className="text-sm">{stage.text}</span>
    </div>
  );
}
