import { useState } from "react";

import { useActivityFeed } from "../../hooks/useActivityFeed";

const dockPanels = [
  { key: "activity", label: "Activity", icon: "A" },
  { key: "claims", label: "Claims", icon: "C" },
  { key: "trades", label: "Trades", icon: "T" },
  { key: "reviews", label: "Reviews", icon: "R" },
];

function panelCount(panelKey, counts) {
  if (panelKey === "activity") return counts.activity;
  if (panelKey === "claims") return counts.claims;
  if (panelKey === "trades") return counts.trades;
  if (panelKey === "reviews") return counts.reviews;
  return 0;
}

export default function RightDock() {
  const [activePanel, setActivePanel] = useState(null);
  const activity = useActivityFeed();

  const expanded = Boolean(activePanel);

  function togglePanel(key) {
    setActivePanel(activePanel === key ? null : key);
  }

  const currentPanel =
    dockPanels.find((panel) => panel.key === activePanel) || dockPanels[0];

  const visibleEvents =
    currentPanel.key === "activity"
      ? activity.events
      : activity.events.filter((event) => event.type === currentPanel.key);

  return (
    <aside className={`right-dock ${expanded ? "expanded" : "collapsed"}`}>
      <div className="dock-icons">
        {dockPanels.map((panel) => {
          const count = panelCount(panel.key, activity.counts);

          return (
            <button
              key={panel.key}
              className={`dock-icon ${activePanel === panel.key ? "active" : ""}`}
              title={panel.label}
              onClick={() => togglePanel(panel.key)}
            >
              <span>{panel.icon}</span>
              {count > 0 && <em>{count}</em>}
            </button>
          );
        })}
      </div>

      <div className="dock-content">
        {expanded && (
          <div className="dock-panel">
            <div className="dock-panel-header">
              <h3>{currentPanel.label}</h3>
              <button onClick={() => setActivePanel(null)}>×</button>
            </div>

            <div className="dock-list">
              {visibleEvents.length === 0 && (
                <div className="dock-item">
                  <strong>No events</strong>
                  <span>Nothing to show for this panel.</span>
                </div>
              )}

              {visibleEvents.map((event) => (
                <div className="dock-item" key={event.id}>
                  <strong>{event.title}</strong>
                  <span>{event.detail}</span>
                  <small>{event.time}</small>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
