import { useEffect, useState } from "react";

import { useIsFetching } from "@tanstack/react-query";

/**
 * A thin bar along the top edge while a page loads data it has never had. Background refetches and live updates
 * (queries that already hold data) do not trigger it, and it waits a moment so fast loads never flash it.
 */
export default function TopLoader() {
  const loading = useIsFetching({ predicate: (q) => q.state.data === undefined }) > 0;
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (!loading) {
      setShown(false);
      return;
    }
    const timer = window.setTimeout(() => setShown(true), 150);
    return () => window.clearTimeout(timer);
  }, [loading]);

  return <div className={`wms-toploader${shown ? " wms-toploader-on" : ""}`} aria-hidden />;
}
