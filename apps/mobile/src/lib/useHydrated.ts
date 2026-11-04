import { useEffect, useState } from "react";

import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { useSession } from "@/stores/session";

const persisted = [useSession, useQueue];

/** Local storage is read asynchronously; render nothing until it is all read, or "signed out" would flash first */
export function useHydrated(): boolean {
  const ready = () => persisted.every((s) => s.persist.hasHydrated());
  const [storesReady, setStoresReady] = useState(ready);
  // Master data is stored in its own file (large) and has its own loaded flag
  const masterReady = useMasterData((s) => s.hydrated);
  useEffect(() => {
    const check = () => setStoresReady(ready());
    const unsubs = persisted.map((s) => s.persist.onFinishHydration(check));
    check();
    return () => unsubs.forEach((u) => u());
  }, []);
  return storesReady && masterReady;
}
