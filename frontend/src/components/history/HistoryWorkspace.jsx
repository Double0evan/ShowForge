import { useEffect, useState } from "react";
import { apiClient } from "../../api/apiClient";
import Panel from "../shared/Panel";
import Button from "../shared/Button";
import Badge from "../shared/Badge";

export default function HistoryWorkspace({ showToast }) {
  const [shows, setShows]         = useState([]);
  const [selected, setSelected]   = useState(null);
  const [showData, setShowData]   = useState(null);
  const [loading, setLoading]     = useState(false);
  const [loadError, setLoadError] = useState("");
  const [activeTab, setActiveTab] = useState("inventory");

  useEffect(() => {
    apiClient.get("/api/history/list")
      .then((r) => setShows(r.shows || []))
      .catch(() => {
        // Fallback: parse from /ui/history which returns Jinja — not ideal
        // We need a JSON endpoint; for now show empty with a note
        setShows([]);
      });
  }, []);

  async function loadShow(showId) {
    setSelected(showId);
    setShowData(null);
    setLoadError("");
    setLoading(true);
    try {
      const r = await apiClient.get(`/api/history/show?show_id=${encodeURIComponent(showId)}`);
      if (!r.ok) throw new Error(r.error || "Failed to load show");
      setShowData(r);
    } catch (e) {
      setLoadError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function downloadZip(showId, variant) {
    const url = `/ui/history/download?show_id=${encodeURIComponent(showId)}&variant=${variant}`;
    window.open(url, "_blank");
  }

  async function deleteShow(showId) {
    if (!window.confirm(`Permanently delete show "${showId}"? This cannot be undone.`)) return;
    try {
      const fd = new FormData();
      fd.append("show_id", showId);
      await apiClient.post("/ui/history/delete", fd);
      showToast?.(`Show "${showId}" deleted.`);
      setShows((s) => s.filter((x) => x.show_id !== showId));
      if (selected === showId) { setSelected(null); setShowData(null); }
    } catch (e) {
      showToast?.(`Delete failed: ${e.message}`);
    }
  }

  return (
    <div className="history-workspace">
      <div className="workspace-header">
        <div>
          <h1>History</h1>
          <p>Browse and download past show data.</p>
        </div>
      </div>

      <div className="history-layout">
        {/* Show list */}
        <Panel title="Past Shows" icon="◫" className="history-list-panel">
          {shows.length === 0 ? (
            <div style={{ color: "var(--muted)", fontSize: 13 }}>No past shows found.</div>
          ) : (
            <div className="history-show-list">
              {shows.map((show) => (
                <div
                  key={show.show_id}
                  className={`history-show-item ${selected === show.show_id ? "active" : ""}`}
                  onClick={() => loadShow(show.show_id)}
                >
                  <div>
                    <strong>{show.show_id}</strong>
                    {show.is_active && (
                      <Badge tone="success" style={{ marginLeft: 8 }}>Active</Badge>
                    )}
                  </div>
                  <div className="history-show-actions" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="history-dl-btn"
                      title="Download watermarked images"
                      onClick={() => downloadZip(show.show_id, "watermarked")}
                    >⬇ WM</button>
                    <button
                      className="history-dl-btn"
                      title="Download raw images"
                      onClick={() => downloadZip(show.show_id, "raw")}
                    >⬇ RAW</button>
                    {!show.is_active && (
                      <button
                        className="history-dl-btn danger"
                        title="Delete show"
                        onClick={() => deleteShow(show.show_id)}
                      >✕</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>

        {/* Show detail */}
        <Panel title={selected || "Select a show"} icon="◧" className="history-detail-panel">
          {!selected && (
            <div style={{ color: "var(--muted)", fontSize: 13 }}>
              Click a show on the left to view its data.
            </div>
          )}

          {loading && (
            <div style={{ color: "var(--muted)", fontSize: 13 }}>Loading...</div>
          )}

          {loadError && (
            <div style={{ color: "var(--red)", fontSize: 13 }}>
              Failed to load: {loadError}
              <p style={{ marginTop: 6, fontSize: 12 }}>
                This show's data may be incomplete or the DB may be from an older version.
              </p>
            </div>
          )}

          {showData && !loading && (
            <>
              {/* Stats row */}
              <div className="stat-grid" style={{ marginBottom: 16 }}>
                <div className="stat-box">
                  <strong>{showData.items?.length || 0}</strong>
                  <span>Items</span>
                </div>
                <div className="stat-box">
                  <strong>{showData.claims?.length || 0}</strong>
                  <span>Claims</span>
                </div>
                <div className="stat-box">
                  <strong>{showData.users?.length || 0}</strong>
                  <span>Users</span>
                </div>
              </div>

              {/* Downloads */}
              <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
                <Button onClick={() => downloadZip(selected, "watermarked")}>⬇ Watermarked ZIP</Button>
                <Button onClick={() => downloadZip(selected, "raw")}>⬇ RAW ZIP</Button>
                <Button onClick={() => downloadZip(selected, "both")}>⬇ Both</Button>
              </div>

              {/* Tabs */}
              <div className="history-tabs">
                {["inventory", "claims", "users"].map((tab) => (
                  <button
                    key={tab}
                    className={`history-tab ${activeTab === tab ? "active" : ""}`}
                    onClick={() => setActiveTab(tab)}
                  >
                    {tab.charAt(0).toUpperCase() + tab.slice(1)}
                  </button>
                ))}
              </div>

              {/* Inventory tab */}
              {activeTab === "inventory" && (
                <table className="inventory-table" style={{ marginTop: 8 }}>
                  <thead>
                    <tr><th>Code</th><th>Status</th><th>Published</th></tr>
                  </thead>
                  <tbody>
                    {(showData.items || []).map((item) => (
                      <tr key={item.item_code}>
                        <td><strong>{item.item_code}</strong></td>
                        <td>{item.status}</td>
                        <td style={{ fontSize: 11, color: "var(--muted)" }}>
                          {item.published_at?.slice(0, 10) || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {/* Claims tab */}
              {activeTab === "claims" && (
                <table className="inventory-table" style={{ marginTop: 8 }}>
                  <thead>
                    <tr><th>Item</th><th>Owner</th><th>Source</th><th>Auction #</th><th>Claimed</th></tr>
                  </thead>
                  <tbody>
                    {(showData.claims || []).map((c) => (
                      <tr key={c.id} style={{ opacity: c.removed_at ? 0.45 : 1 }}>
                        <td><strong>{c.item_code}</strong></td>
                        <td>{c.user_display_name || "—"}</td>
                        <td>{c.source}</td>
                        <td>{c.auction_number ? `#${c.auction_number}` : "—"}</td>
                        <td style={{ fontSize: 11, color: "var(--muted)" }}>
                          {c.created_at?.slice(0, 10) || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {/* Users tab */}
              {activeTab === "users" && (
                <table className="inventory-table" style={{ marginTop: 8 }}>
                  <thead>
                    <tr><th>Name</th><th>Kind</th><th>Claims</th></tr>
                  </thead>
                  <tbody>
                    {(showData.users || []).map((u) => (
                      <tr key={u.id}>
                        <td><strong>{u.display_name}</strong></td>
                        <td>{u.kind}</td>
                        <td>{u.claims || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}
