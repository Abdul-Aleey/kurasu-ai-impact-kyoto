import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { postChat } from "../api/client";
import { ChatBubble } from "../components/ChatBubble";
import { ComposerBar } from "../components/ComposerBar";
import { useAppData } from "../context/AppDataContext";
import { useLocationContext } from "../context/LocationContext";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { useTtsPlayer } from "../hooks/useTtsPlayer";
import { blobToBase64 } from "../utils/blob";
import { stripFormFieldsNote } from "../utils/text";
import type { AgentSummary, Attachment, HistoryTurn, InputMode, Turn } from "../types";

export function ChatScreen() {
  const { agentId = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<AgentSummary | null>(
    (location.state as { agent?: AgentSummary } | null)?.agent ?? null,
  );
  const [agentLoadFailed, setAgentLoadFailed] = useState(false);

  const { agents } = useAppData();
  const { coords, status: locationStatus, retry: retryLocation } = useLocationContext();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [final, setFinal] = useState(false);
  const { loadingIndex, playingIndex, play, prefetch } = useTtsPlayer();

  useEffect(() => {
    // Direct link / page refresh / PWA shortcut launch has no router state --
    // look the agent up by id in the already-fetched (or in-flight) shared
    // agent list instead of bouncing straight back to Home.
    if (agent || !agentId) return;
    if (agents === null) return; // still loading from AppDataProvider
    const found = agents.find((a) => a.id === agentId);
    if (found) setAgent(found);
    else setAgentLoadFailed(true);
  }, [agent, agentId, agents]);

  // Hooks must run unconditionally on every render -- `agent` starts null on
  // a direct link/refresh/PWA shortcut and gets set asynchronously above, so
  // any hook call placed after the early returns below would be called on
  // some renders but not others, which is an invalid, crash-causing pattern.
  const handleRecorded = useCallback(
    async (blob: Blob, mimeType: string) => {
      const dataBase64 = await blobToBase64(blob);
      void send(undefined, [{ mimeType, dataBase64 }], "voice");
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [turns, busy, final, coords, agentId],
  );
  const { isRecording, supported: micSupported, toggleRecording } = useAudioRecorder(handleRecorded);

  const messageListRef = useRef<HTMLDivElement>(null);
  const messageContentRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // A ResizeObserver on the actual content wrapper (not just a `[turns]`
    // effect) is what makes this reliable: the pending "Thinking..." bubble
    // swaps in progressively longer text on its own internal timer (e.g.
    // "Still working on it -- this one's taking a bit longer than usual...")
    // without `turns` itself ever changing, and a loaded image can also grow
    // the content after the initial paint. Any of those makes the list
    // taller *after* an earlier scroll-to-bottom already ran, which is what
    // made the view look like it "scrolled up" instead of following new
    // content -- reacting to the real content height, whatever changed it,
    // fixes all of those causes at once instead of one at a time.
    const container = messageListRef.current;
    const content = messageContentRef.current;
    if (!container || !content) return;

    const scrollToBottom = () => {
      container.scrollTop = container.scrollHeight;
    };
    scrollToBottom();

    const observer = new ResizeObserver(scrollToBottom);
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  if (agentLoadFailed) {
    navigate("/", { replace: true });
    return null;
  }
  if (!agent) {
    return <div className="flex flex-1 items-center justify-center text-white/40">Loading…</div>;
  }

  async function send(text: string | undefined, attachments: Attachment[], inputMode: InputMode) {
    if (busy) return;
    setError(null);
    setFinal(false);

    const userTurn: Turn = { role: "user", text: text ?? "", attachments, inputMode };
    const historyForRequest: HistoryTurn[] = turns.map((t) => ({
      role: t.role, text: t.text, attachments: t.attachments, inputMode: t.inputMode,
      specialistUsed: t.specialistUsed,
    }));
    const modelTurnIndex = turns.length + 1;

    setTurns((prev) => [...prev, userTurn, { role: "model", text: "", pending: true }]);
    setBusy(true);

    try {
      const response = await postChat({
        agentId,
        history: historyForRequest,
        newTurn: { text, attachments, inputMode },
        deviceContext: {
          lat: coords?.lat,
          lng: coords?.lng,
          currentTimeIso: new Date().toISOString(),
        },
      });

      setTurns((prev) => [
        ...prev.slice(0, -1),
        {
          role: "model", text: response.text, generatedFiles: response.generatedFiles,
          specialistUsed: response.specialistUsed,
        },
      ]);
      if (response.status === "final_answer") setFinal(true);
      const spokenText = stripFormFieldsNote(response.text);
      if (inputMode === "voice") {
        void play(modelTurnIndex, spokenText);
      } else {
        // Typed questions don't auto-play, but silently start synthesizing
        // in the background anyway -- if the user does tap the speaker
        // icon afterward, it's then instant (or far along) instead of
        // paying the full synthesis wait at the moment they click.
        prefetch(modelTurnIndex, spokenText);
      }
    } catch (e) {
      setTurns((prev) => prev.slice(0, -1));
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setTurns([]);
    setFinal(false);
    setError(null);
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-gradient-to-b from-[#1a1030] via-[#160e28] to-[#0d0a1a]">
      <header className="flex items-center gap-3 border-b border-white/10 bg-black/20 px-4 py-3 backdrop-blur-md">
        <button onClick={() => navigate("/")} aria-label="Back" className="text-xl text-white/70">
          ←
        </button>
        <div className="text-2xl">{agent.icon}</div>
        <div className="min-w-0 flex-1">
          <div className="truncate font-semibold text-white">{agent.title}</div>
          <div className="truncate text-xs text-white/50">{agent.subtitle}</div>
        </div>
      </header>

      <div ref={messageListRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <div ref={messageContentRef} className="space-y-3">
          {turns.length === 0 && (
            <>
              <ChatBubble turn={{ role: "model", text: agent.welcomeMessage }} />
              {agent.usesLocation && !coords && (
                <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-200">
                  <p className="mb-2">
                    {locationStatus === "denied"
                      ? "Location seems to be blocked. Check your browser's site settings to enable it, or just tell me a nearby station or landmark instead."
                      : "Enable location access for the most accurate results, or just tell me a nearby station or landmark instead."}
                  </p>
                  <button
                    onClick={retryLocation}
                    className="rounded-full bg-amber-400/20 px-3 py-1.5 text-xs font-medium text-amber-100
                               transition hover:bg-amber-400/30"
                  >
                    📍 Enable Location
                  </button>
                </div>
              )}
            </>
          )}
          {turns.map((turn, i) => (
            <ChatBubble
              key={i}
              turn={turn}
              onPlay={turn.text ? () => play(i, stripFormFieldsNote(turn.text)) : undefined}
              isPlaying={playingIndex === i}
              isLoadingAudio={loadingIndex === i}
              longWaitMessage={agent.longWaitMessage}
            />
          ))}
          {error && (
            <div className="rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-200">
              {error}
            </div>
          )}
        </div>
      </div>

      {final && (
        <div className="border-t border-white/10 bg-black/30 px-4 pt-3 backdrop-blur-md">
          <button
            onClick={reset}
            className="w-full rounded-full border border-white/15 py-2 text-sm text-white/70
                       transition hover:bg-white/5"
          >
            Start a new request
          </button>
        </div>
      )}
      <ComposerBar
        disabled={busy}
        onSend={(text, attachments) => send(text, attachments, "typed")}
        micSupported={micSupported}
        isRecording={isRecording}
        onToggleRecording={toggleRecording}
        hasImageInput={agent.hasImageInput}
        maxImages={agent.maxImages}
      />
    </div>
  );
}
