import { useEffect, useMemo, useState } from "react";

import Panel from "../shared/Panel";
import Button from "../shared/Button";
import DataTable from "../shared/DataTable";
import BulkActionBar from "../shared/BulkActionBar";
import FilterBar from "../shared/FilterBar";
import UploadWorkflow from "../uploads/UploadWorkflow";

import InventoryRow from "./InventoryRow";
import InventoryDrawer from "./InventoryDrawer";

import { useInventory } from "../../hooks/useInventory";

export default function InventoryWorkspace({ showToast, setLoading, activeTab }) {
  const [activeItem, setActiveItem] = useState(null);
  const inventory = useInventory({ showToast });

  useEffect(() => { setLoading?.(inventory.loading); }, [inventory.loading, setLoading]);

  const pulseStats = useMemo(() => ({
    total:     inventory.items.length,
    available: inventory.items.filter((i) => i.status === "Available").length,
    published: inventory.items.filter((i) => i.publishedAt && i.status === "Available").length,
    claimed:   inventory.items.filter((i) => i.status === "Claimed").length,
    removed:   inventory.items.filter((i) => i.status === "Removed").length,
  }), [inventory.items]);

  const columns = [
    {
      key: "select",
      label: (
        <input type="checkbox" className="row-checkbox"
          checked={inventory.allVisibleSelected}
          onChange={inventory.toggleAllVisible}
        />
      ),
    },
    { key: "preview", label: "" },
    { key: "code",    label: "Item",    sortable: true },
    { key: "status",  label: "Status",  sortable: true },
    { key: "mode",    label: "Mode",    sortable: false },
    { key: "updated", label: "Updated", sortable: true },
    { key: "actions", label: "" },
  ];

  // ── Upload Queue tab ───────────────────────────────────────────────────────
  if (activeTab === "Upload Queue") {
    return (
      <div className="inventory-workspace">
        <div className="workspace-header">
          <div>
            <h1>Upload Queue</h1>
            <p>Stage images, set rating, and upload to inbox for processing.</p>
          </div>
          <div className="workspace-actions">
            <Button onClick={inventory.reload}>Refresh Inventory</Button>
          </div>
        </div>
        <div style={{ maxWidth: 800 }}>
          <Panel title="Upload" icon="⇧">
            <UploadWorkflow showToast={showToast} onUploaded={inventory.reload} />
          </Panel>
        </div>
      </div>
    );
  }

  // ── Inventory List tab ─────────────────────────────────────────────────────
  return (
    <>
      <div className="inventory-workspace">
        <div className="workspace-header">
          <div>
            <h1>Inventory</h1>
            <p>Publish, assign, and manage show inventory.</p>
          </div>
          <div className="workspace-actions">
            <Button onClick={inventory.reload}>Refresh</Button>
            <Button
              variant="primary"
              onClick={() =>
                inventory.publishItems(
                  inventory.items
                    .filter((i) => i.status === "Available" && !i.publishedAt)
                    .map((i) => i.code)
                )
              }
            >
              Publish All
            </Button>
          </div>
        </div>

        {/* Stats — full width */}
        <Panel title="Show Pulse" icon="⌁" style={{ marginBottom: 16 }}>
          <div className="stat-grid">
            <div className="stat-box"><strong>{pulseStats.total}</strong><span>Total</span></div>
            <div className="stat-box"><strong>{pulseStats.available}</strong><span>Available</span></div>
            <div className="stat-box"><strong>{pulseStats.published}</strong><span>Listed</span></div>
            <div className="stat-box"><strong>{pulseStats.claimed}</strong><span>Claimed</span></div>
            <div className="stat-box"><strong>{pulseStats.removed}</strong><span>Removed</span></div>
          </div>
        </Panel>

        {/* Table — full width */}
        <Panel title="Inventory" icon="◇" className="inventory-panel">
          <FilterBar
            search={inventory.search}
            onSearchChange={inventory.setSearch}
            searchPlaceholder="Search by item code or status..."
            activeFilterCount={inventory.activeFilterCount}
            onClear={inventory.clearFilters}
            filters={[{
              key: "status", label: "Status",
              value: inventory.statusFilter,
              onChange: inventory.setStatusFilter,
              options: inventory.filterOptions.statuses,
            }]}
          />
          <BulkActionBar
            selectedCount={inventory.selectedCodes.length}
            contextLabel="item(s) selected"
            onClear={inventory.clearSelection}
            actions={[
              { key: "publish", label: "Publish Selected", onClick: () => inventory.publishItems(inventory.selectedCodes) },
              { key: "remove",  label: "Remove", variant: "danger", onClick: () => inventory.removeItems(inventory.selectedCodes) },
            ]}
          />
          <DataTable
            columns={columns}
            rows={inventory.pagedItems}
            rowKey={(item) => item.code}
            emptyLabel="No inventory items found."
            className="inventory-data-table"
            sortKey={inventory.sortKey}
            sortDirection={inventory.sortDirection}
            onSort={inventory.changeSort}
            footerLabel={`${inventory.filteredItems.length} of ${inventory.items.length} items`}
            pagination={{
              page: inventory.page, totalPages: inventory.totalPages,
              pageSize: inventory.pageSize,
              onPageChange: inventory.setPage, onPageSizeChange: inventory.setPageSize,
            }}
            renderRow={(item) => (
              <InventoryRow
                key={item.code} item={item}
                selected={inventory.selectedCodes.includes(item.code)}
                onToggle={() => inventory.toggleRow(item.code)}
                onView={() => setActiveItem(item)}
                onPublish={() => inventory.publishItems([item.code])}
              />
            )}
          />
        </Panel>
      </div>

      <InventoryDrawer
        item={activeItem}
        onClose={() => setActiveItem(null)}
        onPublish={async (code) => { await inventory.publishItems([code]); setActiveItem(null); }}
        onRepublish={async (code) => { await inventory.republishItem(code); setActiveItem(null); }}
        onRemove={async (code) => { await inventory.removeItems([code]); setActiveItem(null); }}
        onAssign={async (code, displayName) => { await inventory.assignItem(code, displayName); setActiveItem(null); }}
        showToast={showToast}
      />
    </>
  );
}
