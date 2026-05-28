import { useEffect } from "react";

import Panel from "../shared/Panel";
import Button from "../shared/Button";

import BinManagerRow from "./BinManagerRow";
import BinAssignmentDrawer from "./BinAssignmentDrawer";
import { useBinManager } from "../../hooks/useBinManager";

export default function BinManagerWorkspace({ showToast, setLoading, activeTab }) {
  const bin = useBinManager({ showToast });

  useEffect(() => { setLoading?.(bin.loading); }, [bin.loading, setLoading]);

  // ── Auction Log tab ────────────────────────────────────────────────────────
  if (activeTab === "Auction Log") {
    return (
      <div className="bin-workspace">
        <div className="workspace-header">
          <div><h1>Auction Log</h1><p>Full record of all auction entries this show.</p></div>
          <div className="workspace-actions">
            <Button onClick={bin.reload}>Refresh</Button>
            <Button variant="danger" onClick={bin.clearAuctionLog}>Clear Log</Button>
          </div>
        </div>
        <Panel title="Full Auction Log" icon="▤">
          <table className="inventory-table">
            <colgroup>
              <col style={{ width: 80 }} />
              <col style={{ width: 120 }} />
              <col />
              <col />
              <col style={{ width: 100 }} />
              <col style={{ width: 120 }} />
            </colgroup>
            <thead>
              <tr>
                <th style={{ textAlign: "center" }}>#</th>
                <th>Item</th>
                <th>Whatnot Buyer</th>
                <th>Discord User</th>
                <th>Status</th>
                <th>Logged</th>
              </tr>
            </thead>
            <tbody>
              {bin.auctionRows.length === 0 && (
                <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>No entries.</td></tr>
              )}
              {bin.auctionRows.map((row) => (
                <tr key={row.id} style={{ opacity: row.cardNumber === 0 ? 0.4 : 1 }}>
                  <td style={{ textAlign: "center", fontWeight: 700, color: "var(--accent, #7c6aff)" }}>#{row.position}</td>
                  <td><strong>{row.itemCode}</strong></td>
                  <td>{row.whatnotName || "—"}</td>
                  <td>{row.discordName || "—"}</td>
                  <td>{row.claimed ? "Assigned" : "Pending"}</td>
                  <td style={{ fontSize: 11, color: "var(--muted)" }}>{row.createdAt?.slice(0, 16).replace("T", " ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    );
  }

  // ── Assignment Queue tab (default) ─────────────────────────────────────────
  return (
    <>
      <div className="bin-workspace">
        <div className="workspace-header">
          <div>
            <h1>Bin Manager</h1>
            <p>Host types item number in Discord → paste buyer name → assign.</p>
          </div>
          <div className="workspace-actions">
            <Button onClick={bin.reload}>Refresh</Button>
            <Button variant="danger" onClick={bin.clearAuctionLog}>Clear Log</Button>
          </div>
        </div>

        <Panel title="Queue Status" icon="◉" style={{ marginBottom: 16 }}>
          <div className="stat-grid">
            <div className="stat-box"><strong>{bin.stats.total}</strong><span>Total</span></div>
            <div className="stat-box"><strong>{bin.stats.assigned}</strong><span>Assigned</span></div>
            <div className="stat-box"><strong>{bin.stats.unassigned}</strong><span>Pending</span></div>
          </div>
        </Panel>

        {bin.error && (
          <div style={{ color: "var(--amber)", fontSize: 13, marginBottom: 12 }}>{bin.error}</div>
        )}

        <Panel title="Assignment Queue" icon="▤" className="bin-panel">
          <div style={{ marginBottom: 12, display: "flex", gap: 8, alignItems: "center" }}>
            <input
              className="drawer-input"
              style={{ maxWidth: 300 }}
              placeholder="Search item, buyer name..."
              value={bin.search}
              onChange={(e) => bin.setSearch(e.target.value)}
            />
            <button
              type="button"
              className="bin-insert-btn"
              onClick={() => bin.insertPlaceholder(null)}
              disabled={bin.inserting !== null}
              title="Insert a skip at position #1"
            >
              + Insert at Top
            </button>
          </div>

          {bin.filteredRows.length === 0 ? (
            <div style={{ textAlign: "center", color: "var(--muted)", padding: "32px 0", fontSize: 14 }}>
              No items in queue. Host types an item number in Discord to add one.
            </div>
          ) : (
            <table className="inventory-table bin-table">
              <colgroup>
                <col style={{ width: 90 }} />
                <col style={{ width: 140 }} />
                <col />
                <col />
                <col style={{ width: 100 }} />
                <col style={{ width: 120 }} />
              </colgroup>
              <thead>
                <tr>
                  <th style={{ textAlign: "center" }}>Auction #</th>
                  <th>Item</th>
                  <th>Whatnot Buyer</th>
                  <th>Discord User</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {bin.filteredRows.map((row) => (
                  <BinManagerRow
                    key={row.id}
                    row={row}
                    onOpen={() => bin.setSelectedRow(row)}
                    onDelete={bin.deleteRow}
                    onInsertAfter={bin.insertPlaceholder}
                    inserting={bin.inserting}
                  />
                ))}
              </tbody>
            </table>
          )}

          <div style={{ marginTop: 8, fontSize: 12, color: "var(--muted)" }}>
            {bin.filteredRows.length} row(s)
          </div>
        </Panel>
      </div>

      <BinAssignmentDrawer
        row={bin.selectedRow}
        onClose={() => bin.setSelectedRow(null)}
        onAssign={bin.assignRow}
        onDelete={bin.deleteRow}
        onFindMatch={bin.findMatch}
      />
    </>
  );
}
