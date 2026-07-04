import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { blobToBase64 } from "../utils/blob";
import type { Attachment } from "../types";

interface Props {
  disabled?: boolean;
  onSend: (text: string | undefined, attachments: Attachment[]) => void;
  onToggleRecording?: () => void;
  isRecording?: boolean;
  micSupported?: boolean;
  hasImageInput?: boolean;
  maxImages?: number;
}

interface StagedImage {
  attachment: Attachment;
  previewUrl: string;
}

/** Images are staged (with a preview + remove option) rather than sent the
 * instant they're picked -- lets the user attach up to `maxImages` photos
 * (e.g. multiple pages of a form) and add a caption, all in one message,
 * instead of firing off a separate captionless message per photo. */
export function ComposerBar({
  disabled, onSend, onToggleRecording, isRecording, micSupported,
  hasImageInput, maxImages = 1,
}: Props) {
  const [text, setText] = useState("");
  const [staged, setStaged] = useState<StagedImage[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const wasDisabledRef = useRef(disabled);

  useEffect(() => {
    // A disabled <input> is automatically blurred by the browser -- that's
    // correct while a reply is in flight, but re-enabling it doesn't
    // restore focus on its own, so typing again needed an extra manual tap
    // back into the box. Refocus exactly on the disabled -> enabled
    // transition (not on every render) so a reply arriving hands control
    // straight back to the keyboard.
    if (wasDisabledRef.current && !disabled) {
      inputRef.current?.focus();
    }
    wasDisabledRef.current = disabled;
  }, [disabled]);

  const addFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const room = maxImages - staged.length;
    if (room <= 0) return;

    const converted = await Promise.all(
      Array.from(files)
        .slice(0, room)
        .map(async (file) => ({
          attachment: { mimeType: file.type, dataBase64: await blobToBase64(file) },
          previewUrl: URL.createObjectURL(file),
        })),
    );
    setStaged((prev) => [...prev, ...converted]);
  };

  const removeStaged = (index: number) => {
    setStaged((prev) => {
      URL.revokeObjectURL(prev[index].previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (disabled) return;
    const trimmed = text.trim();
    if (!trimmed && staged.length === 0) return;

    onSend(trimmed || undefined, staged.map((s) => s.attachment));
    staged.forEach((s) => URL.revokeObjectURL(s.previewUrl));
    setStaged([]);
    setText("");
  };

  return (
    <div className="border-t border-white/10 bg-black/30 backdrop-blur-md">
      {staged.length > 0 && (
        <div className="flex gap-2 overflow-x-auto px-3 pt-3">
          {staged.map((s, i) => (
            <div key={i} className="relative shrink-0">
              <img src={s.previewUrl} alt="" className="h-14 w-14 rounded-lg object-cover" />
              <button
                type="button"
                onClick={() => removeStaged(i)}
                aria-label="Remove photo"
                className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center
                           rounded-full bg-black/80 text-xs text-white"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <form onSubmit={submit} className="flex items-center gap-2 p-3">
        {hasImageInput && staged.length < maxImages && (
          <label className="flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center
                             rounded-full bg-white/10 text-lg text-white/80 transition hover:bg-white/20">
            📷
            <input
              type="file"
              accept="image/*"
              multiple={maxImages > 1}
              className="hidden"
              disabled={disabled}
              onChange={(e) => {
                void addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </label>
        )}

        <input
          ref={inputRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
          placeholder={isRecording ? "Listening…" : "Type a message…"}
          className="min-w-0 flex-1 rounded-full border border-white/15 bg-white/5 px-4 py-2.5
                     text-[15px] text-white placeholder-white/40 outline-none
                     focus:border-fuchsia-400/50 disabled:opacity-50"
        />

        {micSupported && onToggleRecording && (
          <button
            type="button"
            onClick={onToggleRecording}
            disabled={disabled}
            aria-label={isRecording ? "Stop recording" : "Record voice message"}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-lg
                        transition disabled:opacity-50
              ${isRecording
                ? "animate-pulse bg-red-500 text-white"
                : "bg-white/10 text-white/80 hover:bg-white/20"}`}
          >
            🎤
          </button>
        )}

        <button
          type="submit"
          disabled={disabled || (!text.trim() && staged.length === 0)}
          aria-label="Send"
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full
                     bg-gradient-to-br from-fuchsia-500 to-indigo-500 text-white shadow-md transition
                     disabled:cursor-not-allowed disabled:opacity-40"
        >
          ↑
        </button>
      </form>
    </div>
  );
}
