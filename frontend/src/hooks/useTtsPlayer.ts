import { useCallback, useRef, useState } from "react";
import { postTts } from "../api/client";

/** Plays at most one message's speech at a time; starting a new one stops
 * whatever was already playing. Tracks loading separately from playing so
 * the UI doesn't claim "Playing" while audio is still being synthesized --
 * a long response can take real time to fetch before any sound starts.
 * Synthesized audio is cached per turn index -- re-tapping the speaker on
 * the same message (e.g. after pausing, or re-listening) reuses the
 * already-fetched clip instead of paying the full synthesis latency again.
 * `prefetch` populates that same cache silently in the background (no
 * loading/playing state change) so a later manual tap on the speaker can
 * be instant instead of waiting on synthesis at click time. */
export function useTtsPlayer() {
  const [loadingIndex, setLoadingIndex] = useState<number | null>(null);
  const [playingIndex, setPlayingIndex] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlCacheRef = useRef<Map<number, string>>(new Map());
  const inFlightRef = useRef<Map<number, Promise<string>>>(new Map());

  // Shared by play() and prefetch() so a manual click while a background
  // prefetch is still in flight reuses that same request instead of firing
  // a duplicate one.
  const fetchAndCache = useCallback((index: number, text: string): Promise<string> => {
    const cached = urlCacheRef.current.get(index);
    if (cached) return Promise.resolve(cached);

    const inFlight = inFlightRef.current.get(index);
    if (inFlight) return inFlight;

    const promise = postTts(text)
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        urlCacheRef.current.set(index, url);
        inFlightRef.current.delete(index);
        return url;
      })
      .catch((e) => {
        inFlightRef.current.delete(index);
        throw e;
      });
    inFlightRef.current.set(index, promise);
    return promise;
  }, []);

  const prefetch = useCallback(
    (index: number, text: string) => {
      void fetchAndCache(index, text);
    },
    [fetchAndCache],
  );

  const play = useCallback(
    async (index: number, text: string) => {
      audioRef.current?.pause();
      setPlayingIndex(null);
      if (!urlCacheRef.current.has(index)) setLoadingIndex(index);

      try {
        const url = await fetchAndCache(index, text);
        const audio = new Audio(url);
        audioRef.current = audio;

        // Deliberately not revoking the object URL here (unlike a one-shot
        // player) -- it's kept alive in urlCacheRef so replaying this same
        // message later is instant instead of re-synthesizing from scratch.
        const clear = () => setPlayingIndex((current) => (current === index ? null : current));
        audio.onended = clear;
        audio.onerror = clear;
        audio.onplaying = () => {
          setLoadingIndex((current) => (current === index ? null : current));
          setPlayingIndex(index);
        };

        await audio.play();
      } catch {
        setLoadingIndex((current) => (current === index ? null : current));
        setPlayingIndex((current) => (current === index ? null : current));
      }
    },
    [fetchAndCache],
  );

  return { loadingIndex, playingIndex, play, prefetch };
}
