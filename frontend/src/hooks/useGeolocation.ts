import { useCallback, useEffect, useState } from "react";

interface Coords {
  lat: number;
  lng: number;
}

export type GeolocationStatus = "pending" | "granted" | "denied" | "unsupported";

interface GeolocationState {
  coords: Coords | null;
  status: GeolocationStatus;
  retry: () => void;
}

/** Best-effort device location; resolves to null on denial/timeout so the
 * orchestrator falls back to asking the user for a landmark instead.
 * Exposes `retry` so the UI can offer an explicit "Enable Location" action --
 * this re-triggers the browser prompt when permission was never decided
 * yet, and is still worth trying after a denial since some browsers do
 * allow a fresh prompt if the user changed their site settings meanwhile. */
export function useGeolocation(): GeolocationState {
  const [coords, setCoords] = useState<Coords | null>(null);
  const [status, setStatus] = useState<GeolocationStatus>("pending");

  const request = useCallback(() => {
    if (!("geolocation" in navigator)) {
      setStatus("unsupported");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setStatus("granted");
      },
      () => {
        setCoords(null);
        setStatus("denied");
      },
      { timeout: 5000, maximumAge: 60_000 },
    );
  }, []);

  useEffect(() => {
    request();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { coords, status, retry: request };
}
