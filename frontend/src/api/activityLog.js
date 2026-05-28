const listeners = new Set();

const initialEvents = [
  {
    id: "evt-inventory-ready",
    type: "inventory",
    title: "Inventory workspace ready",
    detail: "Mock state loaded through ShowForge API layer.",
    time: "just now",
  },
  {
    id: "evt-bin-sync",
    type: "bin",
    title: "Auction log synced",
    detail: "Bin Manager mock queue is available.",
    time: "just now",
  },
  {
    id: "evt-api-mode",
    type: "system",
    title: "API mode: mock",
    detail: "Live FastAPI wiring is deferred.",
    time: "just now",
  },
];

let events = [...initialEvents];

export const activityLog = {
  list() {
    return [...events];
  },

  push(event) {
    const nextEvent = {
      id: event.id || `evt-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      time: event.time || "just now",
      ...event,
    };

    events = [nextEvent, ...events].slice(0, 80);

    listeners.forEach((listener) => listener([...events]));

    return nextEvent;
  },

  subscribe(listener) {
    listeners.add(listener);
    listener([...events]);

    return () => listeners.delete(listener);
  },

  reset() {
    events = [...initialEvents];
    listeners.forEach((listener) => listener([...events]));
  },
};
