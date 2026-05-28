import { useEffect, useState } from "react";

import Panel from "../shared/Panel";
import Button from "../shared/Button";
import Badge from "../shared/Badge";
import DataTable from "../shared/DataTable";
import BulkActionBar from "../shared/BulkActionBar";
import FilterBar from "../shared/FilterBar";

import UserRow from "./UserRow";
import UserDrawer from "./UserDrawer";
import { useUsers } from "../../hooks/useUsers";

export default function UsersWorkspace({ showToast, setLoading, activeTab }) {
  const [activeUser, setActiveUser] = useState(null);
  const [bulkAmount, setBulkAmount] = useState(1);
  const [addingGuest, setAddingGuest] = useState(false);
  const [guestName, setGuestName] = useState("");
  const users = useUsers({ showToast });

  useEffect(() => { setLoading?.(users.loading); }, [users.loading, setLoading]);

  const columns = [
    { key: "select", label: (<input type="checkbox" className="row-checkbox" checked={users.allVisibleSelected} onChange={users.toggleAllVisible} />) },
    { key: "displayName", label: "User", sortable: true },
    { key: "kind", label: "Kind", sortable: true },
    { key: "discordUserId", label: "Discord ID", sortable: false },
    { key: "balance", label: "Credits", sortable: true },
    { key: "cardsOwned", label: "Cards", sortable: true },
    { key: "status", label: "Status", sortable: false },
    { key: "actions", label: "" },
  ];

  async function handleAddGuest() {
    if (!guestName.trim()) return;
    await users.addGuest(guestName.trim());
    setGuestName(""); setAddingGuest(false);
  }

  // ── Merge Review tab ───────────────────────────────────────────────────────
  if (activeTab === "Merge Review") {
    const mergeUsers = users.users.filter((u) => u.mergeCandidate);
    return (
      <div className="users-workspace">
        <div className="workspace-header">
          <div><h1>Merge Review</h1><p>Pending and guest users with potential Discord matches.</p></div>
          <div className="workspace-actions"><Button onClick={users.reload}>Refresh</Button></div>
        </div>
        <Panel title="Merge Candidates" icon="⇄">
          {mergeUsers.length === 0 ? (
            <div style={{ color: "var(--muted)", padding: "24px 0", textAlign: "center" }}>No merge candidates found.</div>
          ) : (
            <table className="inventory-table">
              <thead>
                <tr><th>Guest / Pending</th><th>Kind</th><th>Matches Discord User</th><th>Credits</th><th>Cards</th></tr>
              </thead>
              <tbody>
                {mergeUsers.map((u) => (
                  <tr key={u.id}>
                    <td><strong>{u.displayName}</strong><span style={{ fontSize: 11, color: "var(--muted)", marginLeft: 6 }}>#{u.id}</span></td>
                    <td><Badge tone="accent">{u.kind}</Badge></td>
                    <td><strong style={{ color: "var(--accent)" }}>{u.mergeCandidate}</strong></td>
                    <td>{u.balance}</td>
                    <td>{u.cardsOwned}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 12 }}>
            Merges happen automatically when the Discord user verifies in the server.
          </p>
        </Panel>
      </div>
    );
  }

  // ── All Users tab (default) ────────────────────────────────────────────────
  return (
    <>
      <div className="users-workspace">
        <div className="workspace-header">
          <div><h1>Users</h1><p>Show participants — Discord members, pending, and guest users.</p></div>
          <div className="workspace-actions">
            <Button onClick={users.reload}>Refresh</Button>
            {addingGuest ? (
              <div style={{ display: "flex", gap: 8 }}>
                <input className="drawer-input" placeholder="Display name..." value={guestName}
                  onChange={(e) => setGuestName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddGuest()} autoFocus />
                <Button variant="primary" onClick={handleAddGuest}>Add</Button>
                <Button onClick={() => setAddingGuest(false)}>Cancel</Button>
              </div>
            ) : (
              <Button onClick={() => setAddingGuest(true)}>Add Guest</Button>
            )}
          </div>
        </div>

        <Panel title="User Pulse" icon="♙" style={{ marginBottom: 16 }}>
          <div className="stat-grid">
            <div className="stat-box"><strong>{users.stats.total}</strong><span>Total</span></div>
            <div className="stat-box"><strong>{users.stats.verified}</strong><span>Verified</span></div>
            <div className="stat-box"><strong>{users.stats.pending}</strong><span>Pending</span></div>
            <div className="stat-box"><strong>{users.stats.mergeReview}</strong><span>Merge Review</span></div>
            <div className="stat-box"><strong>{users.stats.credits}</strong><span>Total Credits</span></div>
          </div>
        </Panel>

        <Panel title="Users" icon="♙" className="users-main-panel">
          <FilterBar
            search={users.search} onSearchChange={users.setSearch}
            searchPlaceholder="Search name, Discord ID, kind..."
            activeFilterCount={users.activeFilterCount} onClear={users.clearFilters}
            filters={[
              { key: "kind", label: "Kind", value: users.kindFilter, onChange: users.setKindFilter, options: users.filterOptions.kinds },
              { key: "status", label: "Status", value: users.statusFilter, onChange: users.setStatusFilter, options: users.filterOptions.statuses },
            ]}
          />
          <BulkActionBar
            selectedCount={users.selectedIds.length} contextLabel="user(s) selected"
            onClear={users.clearSelection}
            actions={[{ key: "award", label: `Award +${bulkAmount} Credit${bulkAmount !== 1 ? "s" : ""}`, onClick: () => users.awardCredits(users.selectedIds, bulkAmount) }]}
            extra={
              <input type="number" min={1} max={99} value={bulkAmount}
                onChange={(e) => setBulkAmount(Math.max(1, parseInt(e.target.value) || 1))}
                style={{ width: 55, background: "var(--soft)", border: "1px solid var(--border)", color: "var(--text)", borderRadius: 8, padding: "4px 8px" }}
              />
            }
          />
          <DataTable
            columns={columns} rows={users.pagedUsers} rowKey={(u) => u.id}
            emptyLabel="No users found." className="users-data-table"
            sortKey={users.sortKey} sortDirection={users.sortDirection} onSort={users.changeSort}
            footerLabel={`${users.filteredUsers.length} of ${users.users.length} users`}
            pagination={{ page: users.page, totalPages: users.totalPages, pageSize: users.pageSize, onPageChange: users.setPage, onPageSizeChange: users.setPageSize }}
            renderRow={(user) => (
              <UserRow key={user.id} user={user}
                selected={users.selectedIds.includes(user.id)}
                onToggle={() => users.toggleRow(user.id)}
                onView={() => setActiveUser(user)}
                onAward={(id, amt) => users.awardCredits([id], amt)}
              />
            )}
          />
        </Panel>
      </div>

      <UserDrawer user={activeUser} onClose={() => setActiveUser(null)}
        onAward={async (id, amt) => {
          await users.awardCredits([id], amt);
          const updated = users.users.find((u) => u.id === id);
          if (updated) setActiveUser(updated);
        }}
      />
    </>
  );
}
