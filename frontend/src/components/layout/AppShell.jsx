import { useState, useEffect } from "react";

import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import WorkspaceTabs, { PAGE_TABS } from "./WorkspaceTabs";
import RightDock from "./RightDock";
import CommandPalette from "../command/CommandPalette";

import DashboardWorkspace   from "../dashboard/DashboardWorkspace";
import InventoryWorkspace   from "../inventory/InventoryWorkspace";
import ClaimsWorkspace      from "../claims/ClaimsWorkspace";
import UsersWorkspace       from "../users/UsersWorkspace";
import TradesWorkspace      from "../trades/TradesWorkspace";
import BinManagerWorkspace  from "../bin/BinManagerWorkspace";
import ConsoleWorkspace     from "../console/ConsoleWorkspace";
import SettingsWorkspace    from "../settings/SettingsWorkspace";
import HistoryWorkspace     from "../history/HistoryWorkspace";
import ActivityWorkspace    from "../activity/ActivityWorkspace";
import DatabaseWorkspace    from "../database/DatabaseWorkspace";

import { apiClient } from "../../api/apiClient";

const ALL_PAGES = [
  "Dashboard", "Inventory", "Claims", "Users", "Trades", "Bin Manager",
  "Console", "Settings", "History", "Activity", "Database",
];

function getStoredPage() {
  try { return localStorage.getItem("activePage") || "Dashboard"; } catch { return "Dashboard"; }
}

function getStoredTab(page) {
  try {
    const stored = localStorage.getItem(`activeTab_${page}`);
    const tabs = PAGE_TABS[page];
    if (stored && tabs?.some((t) => t.name === stored)) return stored;
    return tabs?.[0]?.name || "";
  } catch { return PAGE_TABS[page]?.[0]?.name || ""; }
}

function storePage(page) { try { localStorage.setItem("activePage", page); } catch {} }
function storeTab(page, tab) { try { localStorage.setItem(`activeTab_${page}`, tab); } catch {} }

export default function AppShell({ showToast, setLoading }) {
  const [activePage, setActivePage]    = useState(getStoredPage);
  const [activeTab, setActiveTabState] = useState(() => getStoredTab(getStoredPage()));
  const [paletteOpen, setPaletteOpen]  = useState(false);
  const [activeShow, setActiveShow]    = useState(null);

  function navigateTo(page) {
    const tab = getStoredTab(page);
    setActivePage(page); setActiveTabState(tab); storePage(page);
  }

  function setActiveTab(tab) { setActiveTabState(tab); storeTab(activePage, tab); }

  useEffect(() => {
    apiClient.get("/shows/active")
      .then((r) => setActiveShow(r.show_id || null))
      .catch(() => setActiveShow(null));
  }, []);

  useEffect(() => {
    function handleKey(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") { e.preventDefault(); setPaletteOpen((o) => !o); }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  async function handleEndShow() {
    if (!window.confirm("End the active show?")) return;
    try { await apiClient.post("/ui/show/end"); setActiveShow(null); showToast?.("Show ended."); }
    catch (e) { showToast?.(`Failed: ${e.message}`); }
  }

  return (
    <div className="app-shell">
      <Sidebar activePage={activePage} setActivePage={navigateTo} activeShow={activeShow} onEndShow={handleEndShow} />

      <div className="main-area">
        <TopBar onOpenCommandPalette={() => setPaletteOpen(true)} showToast={showToast} />
        <WorkspaceTabs activePage={activePage} activeTab={activeTab} setActiveTab={setActiveTab} />

        <main className="workspace">
          {activePage === "Dashboard"   && <DashboardWorkspace  showToast={showToast} setActivePage={navigateTo} activeTab={activeTab} />}
          {activePage === "Inventory"   && <InventoryWorkspace  showToast={showToast} setLoading={setLoading} activeTab={activeTab} />}
          {activePage === "Claims"      && <ClaimsWorkspace     showToast={showToast} setLoading={setLoading} activeTab={activeTab} />}
          {activePage === "Users"       && <UsersWorkspace      showToast={showToast} setLoading={setLoading} activeTab={activeTab} />}
          {activePage === "Trades"      && <TradesWorkspace     showToast={showToast} activeTab={activeTab} />}
          {activePage === "Bin Manager" && <BinManagerWorkspace showToast={showToast} setLoading={setLoading} activeTab={activeTab} />}
          {activePage === "Console"     && <ConsoleWorkspace    showToast={showToast} activeTab={activeTab} />}
          {activePage === "Settings"    && <SettingsWorkspace   showToast={showToast} activeTab={activeTab} />}
          {activePage === "History"     && <HistoryWorkspace    showToast={showToast} activeTab={activeTab} />}
          {activePage === "Activity"    && <ActivityWorkspace   activeTab={activeTab} />}
          {activePage === "Database"    && <DatabaseWorkspace   activeTab={activeTab} />}
          {!ALL_PAGES.includes(activePage) && (
            <div className="coming-soon"><h1>{activePage}</h1><p>Workspace not wired yet.</p></div>
          )}
        </main>
      </div>

      <RightDock />

      <CommandPalette
        open={paletteOpen} onClose={() => setPaletteOpen(false)}
        activePage={activePage} setActivePage={navigateTo} showToast={showToast}
      />
    </div>
  );
}
