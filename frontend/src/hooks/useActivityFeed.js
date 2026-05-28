import { useEffect, useState } from "react";

import { showforgeApi } from "../api/showforgeApi";

export function useActivityFeed() {
  const [events, setEvents] = useState([]);

  useEffect(() => {
    if (typeof showforgeApi.subscribeActivity === "function") {
      return showforgeApi.subscribeActivity(setEvents);
    }

    let mounted = true;

    showforgeApi.listActivity?.().then((nextEvents) => {
      if (mounted) setEvents(nextEvents || []);
    });

    return () => {
      mounted = false;
    };
  }, []);

  return {
    events,
    latest: events[0] || null,
    counts: {
      activity: events.length,
      claims: events.filter((event) => event.type === "claims").length,
      trades: events.filter((event) => event.type === "trades").length,
      reviews: events.filter((event) => event.type === "review").length,
    },
  };
}
