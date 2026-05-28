import { useEffect, useState, useCallback } from "react";
import { apiClient } from "../../api/apiClient";
import Panel from "../shared/Panel";
import Button from "../shared/Button";

// Small card thumbnail strip
function CardStrip({ cards = [] }) {
  if (!cards.length) return <span style={{ color: "var(--muted)", fontSize: 12 }}>—</span>;
  return (
    <div style={{ display: "flex", gap: 4, flexWrap: "wrap", alignItems: "center" }}>
      {cards.map((c) => (
        <div key={c.item_code} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
          {c.image_url ? (
            <img src={c.image_url} alt={c.item_code}
              style={{ width: 36, height: 36, borderRadius: 6, objectFit: "cover", border: "1px solid rgba(255,255,255,0.1)" }}
              onError={(e) => { e.target.style.display = "none"; }}
            />
          ) : (
            <div style={{ width: 36, height: 36, borderRadius: 6, background: "rgba(124,92,255,0.15)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, color: "var(--accent)", fontWeight: 700 }}>
              {c.item_code}
            </div>
          )}
          <span style={{ fontSize: 9, color: "var(--muted)" }}>{c.item_code}</span>
        </div>
      ))}
    </div>
  );
}

function useTradeData() {
  const [data, setData]       = useState({ channels: [], listings: [], offers: [], completed: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get("/api/trades");
      if (res.ok) setData(res);
      else setError(res.error || "Failed to load");
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);
  return { ...data, loading, error, reload: load };
}

// ── Channels tab ──────────────────────────────────────────────────────────────
function ChannelsTab({ showToast }) {
  const trades = useTradeData();
  const [openUserId, setOpenUserId]    = useState("");
  const [opening, setOpening]          = useState(false);
  const [refreshingAll, setRefreshAll] = useState(false);
  const [closingAll, setClosingAll]    = useState(false);

  async function handleOpen() {
    if (!openUserId.trim()) return;
    setOpening(true);
    try {
      const fd = new FormData(); fd.append("discord_user_id", openUserId.trim());
      const res = await apiClient.post("/api/trades/open_channel", fd);
      showToast?.(res.ok ? "Trade channel opened." : `Failed: ${res.error}`);
      setOpenUserId(""); trades.reload();
    } catch(e) { showToast?.(`Failed: ${e.message}`); }
    finally { setOpening(false); }
  }

  async function handleRefreshAll() {
    setRefreshAll(true);
    try {
      const res = await apiClient.post("/api/trades/refresh_all");
      showToast?.(res.ok ? "All channels refreshed." : `Failed: ${res.error}`);
    } catch(e) { showToast?.(`Failed: ${e.message}`); }
    finally { setRefreshAll(false); }
  }

  async function handleCloseAll() {
    if (!window.confirm("Close ALL trade channels?")) return;
    setClosingAll(true);
    try {
      const res = await apiClient.post("/api/trades/close_all");
      showToast?.(res.ok ? "All channels closed." : `Failed: ${res.error}`);
      trades.reload();
    } catch(e) { showToast?.(`Failed: ${e.message}`); }
    finally { setClosingAll(false); }
  }

  async function handleRefreshUser(userId) {
    try {
      const fd = new FormData(); fd.append("discord_user_id", userId);
      await apiClient.post("/api/trades/refresh_user", fd);
      showToast?.("Channel refreshed.");
    } catch(e) { showToast?.(`Failed: ${e.message}`); }
  }

  async function handleCloseUser(userId, name) {
    if (!window.confirm(`Close trade channel for ${name}?`)) return;
    try {
      const fd = new FormData(); fd.append("discord_user_id", userId);
      await apiClient.post("/api/trades/close_channel", fd);
      showToast?.(`Channel closed for ${name}.`); trades.reload();
    } catch(e) { showToast?.(`Failed: ${e.message}`); }
  }

  return (
    <div className="trades-workspace">
      <div className="workspace-header">
        <div><h1>Trade Channels</h1><p>Manage active trade channels.</p></div>
        <div className="workspace-actions">
          <Button onClick={trades.reload}>Refresh</Button>
          <Button onClick={handleRefreshAll} disabled={refreshingAll}>{refreshingAll ? "Refreshing..." : "Refresh All"}</Button>
          <Button variant="danger" onClick={handleCloseAll} disabled={closingAll}>{closingAll ? "Closing..." : "Close All"}</Button>
        </div>
      </div>

      <Panel title="Overview" icon="↔" style={{ marginBottom: 16 }}>
        <div className="stat-grid">
          <div className="stat-box"><strong>{trades.channels.length}</strong><span>Open Channels</span></div>
          <div className="stat-box"><strong>{trades.listings.length}</strong><span>Active Listings</span></div>
          <div className="stat-box"><strong>{trades.offers.length}</strong><span>Pending Offers</span></div>
          <div className="stat-box"><strong>{trades.completed.length}</strong><span>Completed Trades</span></div>
        </div>
      </Panel>

      <Panel title="Open Channel for User" icon="+" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input className="drawer-input" style={{ maxWidth: 280 }} placeholder="Discord User ID..."
            value={openUserId} onChange={(e) => setOpenUserId(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleOpen()} />
          <Button variant="primary" onClick={handleOpen} disabled={opening || !openUserId.trim()}>
            {opening ? "Opening..." : "Open Channel"}
          </Button>
        </div>
      </Panel>

      <Panel title="Active Channels" icon="↔">
        {trades.loading ? (
          <div style={{ color: "var(--muted)", fontSize: 13 }}>Loading...</div>
        ) : trades.channels.length === 0 ? (
          <div style={{ color: "var(--muted)", fontSize: 13, padding: "12px 0" }}>No active trade channels.</div>
        ) : (
          <table className="inventory-table">
            <thead>
              <tr><th>User</th><th>Discord ID</th><th>Channel ID</th><th>Created</th><th></th></tr>
            </thead>
            <tbody>
              {trades.channels.map((ch) => (
                <tr key={ch.channel_id}>
                  <td><strong>{ch.display_name || "—"}</strong></td>
                  <td className="mono-cell" style={{ fontSize: 11 }}>{ch.user_id}</td>
                  <td className="mono-cell" style={{ fontSize: 11 }}>{ch.channel_id}</td>
                  <td style={{ fontSize: 11, color: "var(--muted)" }}>{ch.created_at?.slice(0, 10) || "—"}</td>
                  <td className="row-actions">
                    <Button onClick={() => handleRefreshUser(ch.user_id)}>Refresh</Button>
                    <Button variant="danger" onClick={() => handleCloseUser(ch.user_id, ch.display_name || ch.user_id)}>Close</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

// ── Trade Log tab ─────────────────────────────────────────────────────────────
function TradeLogTab() {
  const trades = useTradeData();
  const [view, setView] = useState("completed");

  return (
    <div className="trades-workspace">
      <div className="workspace-header">
        <div><h1>Trade Log</h1><p>Completed trades, pending offers, and active listings.</p></div>
        <div className="workspace-actions"><Button onClick={trades.reload}>Refresh</Button></div>
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {[
          { key: "completed", label: `Completed (${trades.completed.length})` },
          { key: "pending",   label: `Pending Offers (${trades.offers.length})` },
          { key: "listings",  label: `Active Listings (${trades.listings.length})` },
        ].map((v) => (
          <button key={v.key} onClick={() => setView(v.key)} style={{
            padding: "6px 14px", borderRadius: 8, fontSize: 13, cursor: "pointer",
            border: "1px solid", transition: "all 0.15s",
            borderColor: view === v.key ? "var(--accent, #7c6aff)" : "rgba(255,255,255,0.1)",
            background:  view === v.key ? "rgba(124,92,255,0.15)" : "transparent",
            color:       view === v.key ? "var(--accent, #7c6aff)" : "var(--muted)",
          }}>{v.label}</button>
        ))}
      </div>

      {view === "completed" && (
        <Panel title="Completed Trades" icon="✓">
          {trades.completed.length === 0
            ? <div style={{ color: "var(--muted)", fontSize: 13 }}>No completed trades yet.</div>
            : trades.completed.map((o) => (
              <div key={o.offer_id} style={{ padding: "12px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", display: "flex", gap: 16, alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, marginBottom: 6 }}>
                    <strong>{o.sender_name || o.sender_user_id}</strong>
                    <span style={{ color: "var(--muted)", margin: "0 8px" }}>→</span>
                    <strong>{o.receiver_name || o.receiver_user_id}</strong>
                  </div>
                  <CardStrip cards={o.cards} />
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap" }}>
                  {o.resolved_at?.slice(0, 16).replace("T", " ") || "—"}
                </div>
              </div>
            ))
          }
        </Panel>
      )}

      {view === "pending" && (
        <Panel title="Pending Offers" icon="⇄">
          {trades.offers.length === 0
            ? <div style={{ color: "var(--muted)", fontSize: 13 }}>No pending offers.</div>
            : trades.offers.map((o) => (
              <div key={o.offer_id} style={{ padding: "12px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", display: "flex", gap: 16, alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, marginBottom: 6 }}>
                    <strong>{o.sender_name || o.sender_user_id}</strong>
                    <span style={{ color: "var(--muted)", margin: "0 8px" }}>offering to</span>
                    <strong>{o.receiver_name || o.receiver_user_id}</strong>
                  </div>
                  <CardStrip cards={o.cards} />
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap" }}>
                  {o.created_at?.slice(0, 16).replace("T", " ") || "—"}
                </div>
              </div>
            ))
          }
        </Panel>
      )}

      {view === "listings" && (
        <Panel title="Active Listings" icon="☰">
          {trades.listings.length === 0
            ? <div style={{ color: "var(--muted)", fontSize: 13 }}>No active listings.</div>
            : trades.listings.map((l) => (
              <div key={l.listing_id} style={{ padding: "12px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", display: "flex", gap: 16, alignItems: "flex-start" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, marginBottom: 4 }}>
                    <strong>{l.owner_name || l.owner_user_id}</strong>
                    {l.looking_for && <span style={{ color: "var(--muted)", fontSize: 12, marginLeft: 8 }}>wants: {l.looking_for}</span>}
                  </div>
                  <CardStrip cards={l.cards} />
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap" }}>
                  {l.created_at?.slice(0, 10) || "—"}
                </div>
              </div>
            ))
          }
        </Panel>
      )}
    </div>
  );
}

export default function TradesWorkspace({ showToast, activeTab }) {
  if (activeTab === "Trade Log") return <TradeLogTab showToast={showToast} />;
  return <ChannelsTab showToast={showToast} />;
}
