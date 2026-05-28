import { useEffect, useState, useCallback, useRef } from "react";
import { apiClient } from "../../api/apiClient";
import Panel from "../shared/Panel";
import Button from "../shared/Button";
import Badge from "../shared/Badge";

const REFRESH_INTERVAL = 20000;

// ── Mini stat chip ────────────────────────────────────────────────────────────
function Chip({ value, label, color }) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
      padding: "10px 14px", borderRadius: 12,
      background: "rgba(255,255,255,0.04)",
      border: "1px solid rgba(255,255,255,0.07)",
      minWidth: 72, flex: 1,
    }}>
      <span style={{ fontSize: 22, fontWeight: 700, color: color || "var(--text)", lineHeight: 1 }}>
        {value ?? "—"}
      </span>
      <span style={{ fontSize: 10, color: "var(--muted)", marginTop: 4, textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {label}
      </span>
    </div>
  );
}

// ── Section label ─────────────────────────────────────────────────────────────
function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, letterSpacing: "0.12em",
      textTransform: "uppercase", color: "var(--muted)",
      marginBottom: 8, paddingBottom: 4,
      borderBottom: "1px solid rgba(255,255,255,0.05)",
    }}>
      {children}
    </div>
  );
}

export default function DashboardWorkspace({ showToast, setActivePage, activeTab }) {
  const [activeShow, setActiveShow]     = useState(null);
  const [showMode, setShowMode]         = useState("standard");
  const [inventory, setInventory]       = useState([]);
  const [claims, setClaims]             = useState([]);
  const [users, setUsers]               = useState([]);
  const [recentClaims, setRecentClaims] = useState([]);
  const [watcher, setWatcher]           = useState(null);
  const [lastRefresh, setLastRefresh]   = useState(null);
  const [togglingMode, setTogglingMode] = useState(false);
  const [showNewForm, setShowNewForm]   = useState(false);
  const [newDate, setNewDate]           = useState(() => new Date().toISOString().slice(0, 10));
  const [newName, setNewName]           = useState("Show");
  const [creating, setCreating]         = useState(false);
  const timerRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const [showRes, invRes, claimsRes, usersRes, binRes] = await Promise.allSettled([
        apiClient.get("/shows/active"),
        apiClient.get("/api/inventory"),
        apiClient.get("/api/claims"),
        apiClient.get("/api/users"),
        apiClient.get("/api/binshow/state"),
      ]);
      if (showRes.status === "fulfilled") {
        setActiveShow(showRes.value.show_id || null);
        setShowMode(showRes.value.show_mode || "standard");
      }
      if (invRes.status === "fulfilled")    setInventory(invRes.value.items || []);
      if (claimsRes.status === "fulfilled") {
        const all = claimsRes.value.claims || [];
        setClaims(all);
        setRecentClaims([...all].filter(c => !c.removed_at).reverse().slice(0, 6));
      }
      if (usersRes.status === "fulfilled")  setUsers(usersRes.value.users || []);
      if (binRes.status === "fulfilled")    setWatcher(binRes.value.watcher || null);
      setLastRefresh(new Date());
    } catch (e) { console.error("Dashboard load error:", e); }
  }, []);

  useEffect(() => {
    load();
    timerRef.current = setInterval(load, REFRESH_INTERVAL);
    return () => clearInterval(timerRef.current);
  }, [load]);

  const inv = {
    total:     inventory.length,
    available: inventory.filter(i => ["available","Available"].includes(i.status)).length,
    listed:    inventory.filter(i => i.published_at && ["available","Available"].includes(i.status)).length,
    claimed:   inventory.filter(i => ["claimed","Claimed"].includes(i.status)).length,
    removed:   inventory.filter(i => ["removed","Removed","claimed_removed"].includes(i.status)).length,
  };
  const activeClaims  = claims.filter(c => !c.removed_at);
  const totalCredits  = users.reduce((s, u) => s + Number(u.balance || 0), 0);
  const verifiedUsers = users.filter(u => u.kind === "discord").length;
  const binClaims     = activeClaims.filter(c => c.source === "bin").length;
  const discordClaims = activeClaims.filter(c => ["button","reaction"].includes(c.source)).length;
  const isBin = showMode === "bin";

  async function toggleMode() {
    const next = isBin ? "standard" : "bin";
    setTogglingMode(true);
    try {
      await apiClient.post(`/shows/mode?mode=${next}`);
      setShowMode(next);
      showToast?.(`Mode → ${next}`);
    } catch(e) { showToast?.(`Failed: ${e.message}`); }
    finally { setTogglingMode(false); }
  }

  async function createShow() {
    if (!newDate || !newName.trim()) return;
    setCreating(true);
    try {
      const fd = new FormData();
      fd.append("date", newDate); fd.append("name", newName.trim());
      const res = await apiClient.post("/ui/show/new", fd);
      if (res.ok) { showToast?.(`"${res.show_id}" created.`); setShowNewForm(false); setNewName("Show"); await load(); }
      else showToast?.(`Failed: ${res.error}`);
    } catch(e) { showToast?.(`Failed: ${e.message}`); }
    finally { setCreating(false); }
  }

  async function endShow() {
    if (!window.confirm(`End "${activeShow}"?`)) return;
    try { await apiClient.post("/ui/show/end"); showToast?.("Show ended."); await load(); }
    catch(e) { showToast?.(`Failed: ${e.message}`); }
  }

  // ── Show Control tab ────────────────────────────────────────────────────────
  if (activeTab === "Stats") {
    return (
      <div className="dashboard-workspace">
        <div className="workspace-header">
          <div><h1>Stats</h1><p>Show-level statistics and breakdowns.</p></div>
          <div className="workspace-actions">
            <span style={{ fontSize: 11, color: "var(--muted)" }}>{lastRefresh ? `Updated ${lastRefresh.toLocaleTimeString()}` : ""}</span>
            <Button onClick={load}>Refresh</Button>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

          <Panel title="Inventory Breakdown" icon="◇">
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                { label: "Total Items",  value: inv.total,     color: "var(--text)" },
                { label: "Available",    value: inv.available, color: "#2ecc71" },
                { label: "Listed (Live)",value: inv.listed,    color: "var(--accent, #7c6aff)" },
                { label: "Claimed",      value: inv.claimed,   color: "#e74c3c" },
                { label: "Removed",      value: inv.removed,   color: "var(--muted)" },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <span style={{ fontSize: 13, color: "var(--muted)" }}>{label}</span>
                  <span style={{ fontSize: 16, fontWeight: 700, color }}>{value}</span>
                </div>
              ))}
              {inv.total > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>Claim rate</div>
                  <div style={{ height: 6, background: "rgba(255,255,255,0.07)", borderRadius: 999, overflow: "hidden" }}>
                    <div style={{
                      height: "100%", borderRadius: 999,
                      background: "linear-gradient(90deg, var(--accent, #7c6aff), #e74c3c)",
                      width: `${Math.round((inv.claimed / inv.total) * 100)}%`,
                      transition: "width 0.5s",
                    }} />
                  </div>
                  <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4, textAlign: "right" }}>
                    {Math.round((inv.claimed / inv.total) * 100)}%
                  </div>
                </div>
              )}
            </div>
          </Panel>

          <Panel title="Claims Breakdown" icon="▣">
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                { label: "Total Active",    value: activeClaims.length, color: "var(--text)" },
                { label: "Bin Show",        value: binClaims,           color: "var(--accent, #7c6aff)" },
                { label: "Discord Button",  value: discordClaims,       color: "#2ecc71" },
                { label: "Direct (Staff)",  value: activeClaims.filter(c => c.source === "staff").length, color: "var(--muted)" },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <span style={{ fontSize: 13, color: "var(--muted)" }}>{label}</span>
                  <span style={{ fontSize: 16, fontWeight: 700, color }}>{value}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Users" icon="♙">
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {[
                { label: "Total Users",     value: users.length,  color: "var(--text)" },
                { label: "Verified Discord",value: verifiedUsers, color: "#2ecc71" },
                { label: "Pending / Guest", value: users.length - verifiedUsers, color: "var(--muted)" },
                { label: "Total Credits",   value: totalCredits,  color: "var(--accent, #7c6aff)" },
                { label: "Avg Credits",     value: users.length ? (totalCredits / users.length).toFixed(1) : "—", color: "var(--muted)" },
              ].map(({ label, value, color }) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                  <span style={{ fontSize: 13, color: "var(--muted)" }}>{label}</span>
                  <span style={{ fontSize: 16, fontWeight: 700, color }}>{value}</span>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Top Claimers" icon="◎">
            {(() => {
              const counts = {};
              activeClaims.forEach(c => {
                const name = c.user_display_name || "Unknown";
                counts[name] = (counts[name] || 0) + 1;
              });
              const top = Object.entries(counts).sort((a,b) => b[1]-a[1]).slice(0, 8);
              return top.length === 0
                ? <div style={{ color: "var(--muted)", fontSize: 13 }}>No claims yet.</div>
                : top.map(([name, count], i) => (
                  <div key={name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 11, color: "var(--muted)", width: 16 }}>#{i+1}</span>
                      <span style={{ fontSize: 13 }}>{name}</span>
                    </div>
                    <span style={{ fontSize: 14, fontWeight: 700, color: i === 0 ? "#f1c40f" : "var(--text)" }}>{count}</span>
                  </div>
                ));
            })()}
          </Panel>
        </div>
      </div>
    );
  }

  // ── Show Control tab (default) ──────────────────────────────────────────────
  return (
    <div className="dashboard-workspace">
      <div className="workspace-header">
        <div><h1>Dashboard</h1><p>Show control and live overview.</p></div>
        <div className="workspace-actions">
          <span style={{ fontSize: 11, color: "var(--muted)" }}>{lastRefresh ? `Updated ${lastRefresh.toLocaleTimeString()}` : "Loading..."}</span>
          <Button onClick={load}>Refresh</Button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>

        {/* Left column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Show Control */}
          <Panel title="Show Control" icon="◉">
            {activeShow ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

                {/* Show name + mode badge */}
                <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: "rgba(255,255,255,0.03)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.07)" }}>
                  <span className="show-live-dot" />
                  <span style={{ fontWeight: 600, fontSize: 14, flex: 1 }}>{activeShow}</span>
                  <Badge tone={isBin ? "accent" : "success"}>{isBin ? "Bin" : "Standard"}</Badge>
                </div>

                {/* Mode toggle */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 2 }}>
                      {isBin ? "Bin Show Mode" : "Standard Mode"}
                    </div>
                    <div style={{ fontSize: 11, color: "var(--muted)" }}>
                      {isBin ? "Host types numbers in Discord" : "Users claim via Discord button"}
                    </div>
                  </div>
                  <button type="button" onClick={toggleMode} disabled={togglingMode}
                    style={{ flexShrink: 0, width: 48, height: 26, borderRadius: 999, border: "none", cursor: "pointer", outline: "none", position: "relative", transition: "background 0.2s", background: isBin ? "var(--accent, #7c6aff)" : "rgba(255,255,255,0.1)" }}>
                    <span style={{ position: "absolute", top: 3, width: 20, height: 20, borderRadius: "50%", background: "white", transition: "left 0.2s", boxShadow: "0 1px 4px rgba(0,0,0,0.3)", left: isBin ? 25 : 3 }} />
                  </button>
                </div>

                {/* Quick actions row */}
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", paddingTop: 4, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                  <Button variant="primary" onClick={() => apiClient.post("/ui/publish_all").then(() => { showToast?.("Publish all sent."); load(); })}>
                    Publish All
                  </Button>
                  <Button onClick={() => { const fd = new FormData(); fd.append("rating","sfw"); apiClient.post("/ui/claims/summary", fd).then(() => showToast?.("SFW summary posted.")); }}>
                    SFW Summary
                  </Button>
                  <Button onClick={() => { const fd = new FormData(); fd.append("rating","nsfw"); apiClient.post("/ui/claims/summary", fd).then(() => showToast?.("NSFW summary posted.")); }}>
                    NSFW Summary
                  </Button>
                </div>

                <Button variant="danger" onClick={endShow}>End Show</Button>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 14px", background: "rgba(255,255,255,0.03)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.07)" }}>
                  <span className="show-live-dot off" />
                  <span style={{ color: "var(--muted)", fontSize: 13 }}>No active show</span>
                </div>
                {showNewForm ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <div>
                      <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 4 }}>Date</label>
                      <input className="drawer-input" type="date" value={newDate} onChange={e => setNewDate(e.target.value)} />
                    </div>
                    <div>
                      <label style={{ fontSize: 11, color: "var(--muted)", display: "block", marginBottom: 4 }}>Show Name</label>
                      <input className="drawer-input" value={newName} onChange={e => setNewName(e.target.value)} placeholder="e.g. May Grand Line Break" onKeyDown={e => e.key === "Enter" && createShow()} />
                    </div>
                    <div style={{ display: "flex", gap: 8 }}>
                      <Button variant="primary" onClick={createShow} disabled={creating}>{creating ? "Creating..." : "Create Show"}</Button>
                      <Button onClick={() => setShowNewForm(false)}>Cancel</Button>
                    </div>
                  </div>
                ) : (
                  <Button variant="primary" onClick={() => setShowNewForm(true)}>+ New Show</Button>
                )}
              </div>
            )}
          </Panel>

          {/* Watcher */}
          <Panel title="Watcher" icon="◎">
            {watcher ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", background: "rgba(255,255,255,0.03)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.07)" }}>
                  <span className={`show-live-dot ${watcher.running ? "" : "off"}`} />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{watcher.running ? (watcher.processing ? "Processing" : "Running") : "Stopped"}</div>
                    <div style={{ fontSize: 11, color: "var(--muted)" }}>{watcher.lastEvent}</div>
                  </div>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <Button onClick={() => apiClient.post("/ui/watcher/start").then(() => { showToast?.("Watcher started."); load(); })}>Start</Button>
                  <Button onClick={() => apiClient.post("/ui/watcher/stop").then(() => { showToast?.("Watcher stopped."); load(); })}>Stop</Button>
                </div>
              </div>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: 13 }}>Watcher status unavailable.</div>
            )}
          </Panel>

          {/* Nav shortcuts */}
          <Panel title="Navigate" icon="▹">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {["Inventory", "Claims", "Users", "Bin Manager", "Console", "History"].map(page => (
                <button key={page} onClick={() => setActivePage?.(page)}
                  style={{ padding: "10px 12px", borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.03)", color: "var(--text)", cursor: "pointer", fontSize: 13, textAlign: "left", transition: "background 0.15s" }}
                  onMouseEnter={e => e.target.style.background = "rgba(124,92,255,0.12)"}
                  onMouseLeave={e => e.target.style.background = "rgba(255,255,255,0.03)"}
                >
                  → {page}
                </button>
              ))}
            </div>
          </Panel>
        </div>

        {/* Right column */}
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Live pulse — compact chips */}
          <Panel title="Live Pulse" icon="⌁">
            <SectionLabel>Inventory</SectionLabel>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
              <Chip value={inv.total}     label="Total" />
              <Chip value={inv.available} label="Available" color="#2ecc71" />
              <Chip value={inv.listed}    label="Listed"    color="var(--accent, #7c6aff)" />
              <Chip value={inv.claimed}   label="Claimed"   color="#e74c3c" />
            </div>
            <SectionLabel>Participants</SectionLabel>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Chip value={users.length}        label="Users" />
              <Chip value={activeClaims.length} label="Claims"  color="var(--accent, #7c6aff)" />
              <Chip value={totalCredits}        label="Credits" color="#2ecc71" />
            </div>
          </Panel>

          {/* Recent claims */}
          <Panel title="Recent Claims" icon="▣">
            {recentClaims.length === 0 ? (
              <div style={{ color: "var(--muted)", fontSize: 13, padding: "8px 0" }}>No claims yet.</div>
            ) : (
              <>
                {recentClaims.map(c => (
                  <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 0", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                    <span style={{ fontWeight: 700, fontSize: 13, minWidth: 48, color: "var(--accent, #7c6aff)" }}>{c.item_code}</span>
                    <span style={{ flex: 1, fontSize: 13 }}>{c.user_display_name || "—"}</span>
                    <Badge tone={c.source === "bin" ? "accent" : "default"}>{c.source}</Badge>
                    <span style={{ fontSize: 11, color: "var(--muted)", minWidth: 38, textAlign: "right" }}>{c.created_at?.slice(11,16) || "—"}</span>
                  </div>
                ))}
                <div style={{ marginTop: 10 }}>
                  <Button onClick={() => setActivePage?.("Claims")}>View All Claims</Button>
                </div>
              </>
            )}
          </Panel>

        </div>
      </div>

      <div style={{ marginTop: 12, fontSize: 11, color: "var(--muted)", textAlign: "right" }}>
        Auto-refreshes every 20s
      </div>
    </div>
  );
}
