import { useState, useEffect } from "react";

const navSections = [
  {
    label: "SHOW",
    pages: [
      { name: "Dashboard",   icon: "▦" },
      { name: "Inventory",   icon: "◇" },
      { name: "Claims",      icon: "▣" },
      { name: "Users",       icon: "♙" },
      { name: "Trades",      icon: "↔" },
    ],
  },
  {
    label: "TOOLS",
    pages: [
      { name: "Bin Manager", icon: "◎" },
      { name: "Console",     icon: "▹" },
      { name: "History",     icon: "↺" },
    ],
  },
  {
    label: "CONFIG",
    pages: [
      { name: "Database",    icon: "▤" },
      { name: "Settings",    icon: "⚙" },
    ],
  },
];

export default function Sidebar({ activePage, setActivePage, activeShow, onEndShow }) {
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem("sidebar_collapsed") === "true"; } catch { return false; }
  });

  // Stamp class on app-shell so the layout responds
  useEffect(() => {
    const shell = document.querySelector(".app-shell");
    if (!shell) return;
    if (collapsed) {
      shell.classList.add("sidebar-is-collapsed");
    } else {
      shell.classList.remove("sidebar-is-collapsed");
    }
  }, [collapsed]);

  function toggleCollapse() {
    const next = !collapsed;
    setCollapsed(next);
    try { localStorage.setItem("sidebar_collapsed", String(next)); } catch {}
  }

  return (
    <aside className={`sidebar ${collapsed ? "sidebar-collapsed" : ""}`}>
      <div className="sidebar-logo" style={{ justifyContent: collapsed ? "center" : undefined }}>
        <div className="logo-mark">S</div>
        {!collapsed && (
          <div>
            <div className="logo-text">ShowForge</div>
            <div className="logo-subtitle">SHOW MANAGER</div>
          </div>
        )}
      </div>

      <nav className="sidebar-nav">
        {navSections.map((section) => (
          <div className="nav-section" key={section.label}>
            {!collapsed && <div className="nav-section-label">{section.label}</div>}
            {section.pages.map((page) => (
              <button
                key={page.name}
                className={`nav-item ${activePage === page.name ? "active" : ""}`}
                onClick={() => setActivePage(page.name)}
                type="button"
                title={page.name}
                style={collapsed ? { justifyContent: "center", padding: "10px 0" } : {}}
              >
                <span className="nav-icon">{page.icon}</span>
                {!collapsed && <span>{page.name}</span>}
              </button>
            ))}
          </div>
        ))}
      </nav>

      {!collapsed ? (
        <div className="active-show-card" style={{
          borderColor: activeShow ? "rgba(46,204,113,0.2)" : "rgba(231,76,60,0.2)",
          background:  activeShow ? undefined : "rgba(231,76,60,0.06)",
        }}>
          <div className="show-label">ACTIVE SHOW</div>
          <div className="show-status-row">
            <span className="show-live-dot" style={{ background: activeShow ? "#2ecc71" : "#e74c3c" }} />
            <div className="show-name" style={{ color: activeShow ? undefined : "#e74c3c" }}>
              {activeShow || "No active show"}
            </div>
          </div>
          {activeShow && (
            <div className="show-card-actions">
              <button className="show-btn danger" onClick={onEndShow}>End</button>
            </div>
          )}
        </div>
      ) : (
        <div style={{ padding: "12px 0", display: "flex", justifyContent: "center" }}>
          <span
            className="show-live-dot"
            style={{ background: activeShow ? "#2ecc71" : "#e74c3c" }}
            title={activeShow || "No active show"}
          />
        </div>
      )}

      <button className="collapse-sidebar" type="button" onClick={toggleCollapse}
        style={collapsed ? { textAlign: "center", padding: "10px 0" } : {}}>
        {collapsed ? "→" : "← Collapse"}
      </button>
    </aside>
  );
}
