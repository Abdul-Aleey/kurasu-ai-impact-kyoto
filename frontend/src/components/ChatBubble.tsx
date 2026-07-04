import ReactMarkdown from "react-markdown";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { stripFormFieldsNote } from "../utils/text";
import type { Turn } from "../types";

interface Props {
  turn: Turn;
  onPlay?: () => void;
  isPlaying?: boolean;
  isLoadingAudio?: boolean;
  longWaitMessage?: string;
}

export function ChatBubble({ turn, onPlay, isPlaying, isLoadingAudio, longWaitMessage }: Props) {
  const isUser = turn.role === "user";
  const hasVoiceAttachment = turn.inputMode === "voice" && isUser;
  const imageAttachments = isUser
    ? (turn.attachments?.filter((a) => a.mimeType.startsWith("image/")) ?? [])
    : [];

  return (
    <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[88%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed shadow-md
          ${isUser
            ? "rounded-br-sm bg-gradient-to-br from-fuchsia-500 to-indigo-500 text-white"
            : "rounded-bl-sm border border-slate-200 bg-slate-50 text-slate-900"}`}
      >
        {imageAttachments.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {imageAttachments.map((a, i) => (
              <img
                key={i}
                src={`data:${a.mimeType};base64,${a.dataBase64}`}
                alt="Attached photo"
                className="h-20 w-20 rounded-lg object-cover"
              />
            ))}
          </div>
        )}

        {turn.pending ? (
          <ThinkingIndicator finalStageMessage={longWaitMessage} />
        ) : hasVoiceAttachment ? (
          <span className="inline-flex items-center gap-2">🎤 Voice message</span>
        ) : turn.text ? (
          <div
            className={`max-w-none text-[15px] ${
              isUser
                ? `prose prose-invert prose-sm prose-p:my-1 prose-headings:my-2 font-medium
                   prose-p:text-white prose-headings:text-white prose-strong:text-white prose-li:text-white`
                : `prose prose-sm prose-slate
                   prose-headings:mb-1 prose-headings:mt-4 first:prose-headings:mt-0
                   prose-h3:text-lg prose-h3:font-bold prose-h3:text-slate-900
                   prose-h3:border-l-4 prose-h3:border-indigo-400 prose-h3:pl-3
                   prose-p:my-1.5 prose-p:text-slate-800
                   prose-li:my-0.5 prose-li:text-slate-800 prose-ul:my-2
                   prose-strong:text-slate-950
                   prose-a:text-indigo-700 prose-a:font-medium prose-a:no-underline hover:prose-a:underline`
            }`}
          >
            <ReactMarkdown>{isUser ? turn.text : stripFormFieldsNote(turn.text)}</ReactMarkdown>
          </div>
        ) : null}

        {!isUser && turn.generatedFiles && turn.generatedFiles.length > 0 && (
          <div className="mt-3 grid grid-cols-2 gap-2">
            {turn.generatedFiles.map((f, i) => (
              <a
                key={i}
                href={`data:${f.mimeType};base64,${f.dataBase64}`}
                download={f.filename}
                className="group relative block overflow-hidden rounded-xl border border-indigo-200
                           bg-white shadow-sm transition hover:border-indigo-400"
              >
                <img
                  src={`data:${f.mimeType};base64,${f.dataBase64}`}
                  alt={f.filename}
                  className="h-36 w-full object-cover"
                />
                <div className="absolute inset-x-0 bottom-0 truncate bg-black/60 px-2 py-1
                                 text-xs text-white">
                  ⬇ {f.filename}
                </div>
              </a>
            ))}
          </div>
        )}

        {!isUser && !turn.pending && onPlay && (
          <button
            onClick={onPlay}
            disabled={isLoadingAudio}
            aria-label="Play message"
            className="mt-2 inline-flex items-center gap-1 text-xs text-slate-400 transition hover:text-slate-700 disabled:opacity-60"
          >
            {isLoadingAudio ? "⏳" : isPlaying ? "⏸" : "🔊"}{" "}
            {isLoadingAudio ? "Loading…" : isPlaying ? "Playing…" : "Listen"}
          </button>
        )}
      </div>
    </div>
  );
}
