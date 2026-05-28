const PAGE_TABS = {
  Dashboard:    [{ name: "Show Control", icon: "◉" }, { name: "Stats", icon: "▦" }],
  Inventory:    [{ name: "Inventory List", icon: "◇" }, { name: "Upload Queue", icon: "⇧" }],
  Claims:       [{ name: "Active", icon: "▣" }, { name: "Removed", icon: "✕" }, { name: "Summary", icon: "☰" }],
  Users:        [{ name: "All Users", icon: "♙" }, { name: "Merge Review", icon: "⇄" }],
  Trades:       [{ name: "Channels", icon: "↔" }, { name: "Trade Log", icon: "☰" }],
  "Bin Manager":[{ name: "Assignment Queue", icon: "◎" }, { name: "Auction Log", icon: "▤" }],
  Console:      [{ name: "Commands", icon: "▹" }, { name: "Live Log", icon: "◎" }],
  Settings:     [{ name: "Watcher", icon: "◎" }, { name: "Discord", icon: "#" }, { name: "Templates", icon: "◈" }],
  History:      [{ name: "Past Shows", icon: "↺" }],
  Database:     [{ name: "Tables", icon: "▤" }],
  Activity:     [{ name: "Feed", icon: "A" }],
};

export default function WorkspaceTabs({ activePage, activeTab, setActiveTab }) {
  const tabs = PAGE_TABS[activePage] || [];
  if (tabs.length === 0) return null;

  return (
    <div className="workspace-tabs-wrap">
      <div className="workspace-label">WORKSPACE</div>
      <div className="workspace-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.name}
            className={`workspace-tab ${activeTab === tab.name ? "active" : ""}`}
            onClick={() => setActiveTab(tab.name)}
            type="button"
          >
            <span>{tab.icon}</span>
            {tab.name}
          </button>
        ))}
      </div>
    </div>
  );
}

export { PAGE_TABS };
