import { createContext, useContext } from "react";
import { useGeolocation } from "../hooks/useGeolocation";
import type { GeolocationStatus } from "../hooks/useGeolocation";

interface Coords {
  lat: number;
  lng: number;
}

interface LocationContextValue {
  coords: Coords | null;
  status: GeolocationStatus;
  retry: () => void;
}

const LocationContext = createContext<LocationContextValue>({
  coords: null,
  status: "pending",
  retry: () => {},
});

/** Requests device location once, as soon as the app opens, so it's already
 * available by the time the user starts a conversation -- agents that need
 * location (clinic finder, restaurant guide, disaster help) can use it
 * silently instead of asking for a landmark. Also exposes `retry` and
 * `status` so any screen can offer an explicit "Enable Location" action
 * when it's still missing. */
export function LocationProvider({ children }: { children: React.ReactNode }) {
  const geolocation = useGeolocation();
  return <LocationContext.Provider value={geolocation}>{children}</LocationContext.Provider>;
}

export function useLocationContext(): LocationContextValue {
  return useContext(LocationContext);
}
