import { useEffect, useState } from "react";

import Panel from "../shared/Panel";
import Button from "../shared/Button";
import DataTable from "../shared/DataTable";
import BulkActionBar from "../shared/BulkActionBar";
import FilterBar from "../shared/FilterBar";

import ClaimsRow from "./ClaimsRow";
import ClaimsDrawer from "./ClaimsDrawer";
import { useClaims } from "../../hooks/useClaims";

export default function ClaimsWorkspace({ showToast, setLoading, activeTab }) {
  const [activeClaim, setActiveClaim] = useState(null);
  const claims = useClaims({ showToast });

  useEffect(() => { setLoading?.(claims.loading); }, [claims.loading, setLoading]);

  const activeColumns = [
    { key: "select", label: (<input type="checkbox" className="row-checkbox" checked={claims.allVisibleSelected} onChange={claims.toggleAllVisible} />) },
    { key: "itemCode", label: "Item", sortable: true },
    { key: "owner", label: "User", sortable: true },
    { key: "source", label: "Source", sortable: true },
    { key: "auctionNumber", label: "Auction #", sortable: true },
    { key: "createdAt", label: "Claimed", sortable: true },
    { key: "actions", label: "" },
  ];

  // ── Summary tab ────────────────────────────────────────────────────────────
  if (activeTab === "Summary") {
    return (
      <div className="claims-workspace">
        <div className="workspace-header">
          <div><h1>Claims Summary</h1><p>Post the show summary to Discord archival threads.</p></div>
        </div>
        <Panel title="Post Summary" icon="☰" style={{ maxWidth: 500 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <strong style={{ fontSize: 13 }}>SFW Summary</strong>
              <p style={{ fontSize: 12, color: "var(--muted)", margin: "4px 0 10px" }}>
                Posts all SFW claims sorted by user to the SFW archival thread.
              </p>
              <Button variant="primary" onClick={() => claims.postSummary("sfw")}>Post SFW Summary</Button>
            </div>
            <div style={{ borderTop: "1px solid var(--border2)", paddingTop: 16 }}>
              <strong style={{ fontSize: 13 }}>NSFW Summary</strong>
              <p style={{ fontSize: 12, color: "var(--muted)", margin: "4px 0 10px" }}>
                Posts all NSFW claims sorted by user to the NSFW archival thread.
              </p>
              <Button variant="primary" onClick={() => claims.postSummary("nsfw")}>Post NSFW Summary</Button>
            </div>
          </div>
        </Panel>
      </div>
    );
  }

  // ── Removed tab ────────────────────────────────────────────────────────────
  if (activeTab === "Removed") {
    const removedClaims = claims.claims.filter((c) => c.status === "Removed");
    return (
      <div className="claims-workspace">
        <div className="workspace-header">
          <div><h1>Removed Claims</h1><p>Historical record of removed and refunded claims.</p></div>
          <div className="workspace-actions"><Button onClick={claims.reload}>Refresh</Button></div>
        </div>
        <Panel title="Removed Claims" icon="✕">
          <table className="inventory-table">
            <thead>
              <tr><th>Item</th><th>User</th><th>Source</th><th>Removed</th><th>Reason</th></tr>
            </thead>
            <tbody>
              {removedClaims.length === 0 && (
                <tr><td colSpan={5} style={{ textAlign: "center", color: "var(--muted)", padding: 24 }}>No removed claims.</td></tr>
              )}
              {removedClaims.map((c) => (
                <tr key={c.id} style={{ opacity: 0.7 }}>
                  <td><strong>{c.itemCode}</strong></td>
                  <td>{c.owner}</td>
                  <td>{c.source}</td>
                  <td style={{ fontSize: 11, color: "var(--muted)" }}>{c.removedAt?.slice(0, 10) || "—"}</td>
                  <td style={{ fontSize: 11, color: "var(--muted)" }}>{c.removedReason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    );
  }

  // ── Active tab (default) ───────────────────────────────────────────────────
  return (
    <>
      <div className="claims-workspace">
        <div className="workspace-header">
          <div><h1>Claims</h1><p>Review, refund, and manage active show claims.</p></div>
          <div className="workspace-actions">
            <Button onClick={claims.reload}>Refresh</Button>
          </div>
        </div>

        <Panel title="Claim Pulse" icon="▣" style={{ marginBottom: 16 }}>
          <div className="stat-grid">
            <div className="stat-box"><strong>{claims.pulseStats.total}</strong><span>Total</span></div>
            <div className="stat-box"><strong>{claims.pulseStats.active}</strong><span>Active</span></div>
            <div className="stat-box"><strong>{claims.pulseStats.bin}</strong><span>Bin</span></div>
            <div className="stat-box"><strong>{claims.pulseStats.direct}</strong><span>Direct</span></div>
            <div className="stat-box"><strong>{claims.pulseStats.discord}</strong><span>Discord</span></div>
          </div>
        </Panel>

        <Panel title="Ownership Ledger" icon="⇅" className="claims-panel">
          <FilterBar
            search={claims.search} onSearchChange={claims.setSearch}
            searchPlaceholder="Search item, user, source, auction #..."
            activeFilterCount={claims.activeFilterCount} onClear={claims.clearFilters}
            filters={[
              { key: "source", label: "Source", value: claims.sourceFilter, onChange: claims.setSourceFilter, options: claims.filterOptions.sources },
              { key: "rating", label: "Rating", value: claims.ratingFilter, onChange: claims.setRatingFilter, options: claims.filterOptions.ratings },
            ]}
          />
          <BulkActionBar
            selectedCount={claims.selectedIds.length} contextLabel="claim(s) selected"
            onClear={claims.clearSelection}
            actions={[{ key: "refund", label: "Remove + Refund", variant: "danger", onClick: () => claims.bulkRemoveRefund(claims.selectedIds) }]}
          />
          <DataTable
            columns={activeColumns} rows={claims.pagedClaims}
            rowKey={(c) => c.id} emptyLabel="No active claims."
            className="claims-data-table" sortKey={claims.sortKey}
            sortDirection={claims.sortDirection} onSort={claims.changeSort}
            footerLabel={`${claims.filteredClaims.length} of ${claims.claims.filter(c => c.status === "Active").length} active claims`}
            pagination={{ page: claims.page, totalPages: claims.totalPages, pageSize: claims.pageSize, onPageChange: claims.setPage, onPageSizeChange: claims.setPageSize }}
            renderRow={(claim) => (
              <ClaimsRow key={claim.id} claim={claim}
                selected={claims.selectedIds.includes(claim.id)}
                onToggle={() => claims.toggleRow(claim.id)}
                onView={() => setActiveClaim(claim)}
                onRemoveRefund={claims.removeClaim}
              />
            )}
          />
        </Panel>
      </div>

      <ClaimsDrawer
        claim={activeClaim} onClose={() => setActiveClaim(null)}
        onSetAuction={async (itemCode, auctionNumber) => {
          await claims.setAuctionNumber(itemCode, auctionNumber);
          const updated = claims.claims.find((c) => c.itemCode === itemCode);
          if (updated) setActiveClaim(updated);
        }}
        onRemoveRefund={async (itemCode, refund) => { await claims.removeClaim(itemCode, refund); setActiveClaim(null); }}
      />
    </>
  );
}
