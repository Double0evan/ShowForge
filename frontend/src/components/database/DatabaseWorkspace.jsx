import { useState } from "react";

import Panel from "../shared/Panel";
import Button from "../shared/Button";

const tables = {
  users: [
    {
      id: 1,
      username: "MiniBinkks",
      type: "discord",
    },
    {
      id: 2,
      username: "Jay",
      type: "guest",
    },
  ],

  claims: [
    {
      item_code: "N092",
      owner: "MiniBinkks",
      auction: 92,
    },
    {
      item_code: "N094",
      owner: "Jay",
      auction: 94,
    },
  ],

  inventory_items: [
    {
      code: "N091",
      status: "Available",
    },
    {
      code: "N092",
      status: "Claimed",
    },
  ],

  voucher_ledger: [],

  media_assets: [],

  auction_log: [
    {
      auction: 91,
      item: "N091",
    },
  ],

  pending_sales: [],
};

export default function DatabaseWorkspace() {
  const [activeTable, setActiveTable] =
    useState("users");

  const [editMode, setEditMode] =
    useState(false);

  const [search, setSearch] = useState("");

  const rows = (tables[activeTable] || []).filter((row) => {
    const query = search.toLowerCase().trim();

    if (!query) return true;

    return Object.values(row).some((value) =>
        String(value).toLowerCase().includes(query)
    );
  });

  const modeLabel = editMode
  ? "Editing enabled for safe fields"
  : "Read-only inspection mode";

  const columns =
    rows.length > 0
      ? Object.keys(rows[0])
      : [];

  return (
    <div className="database-workspace">
      <div className="workspace-header">
        <div>
          <h1>Database Manager</h1>

          <p>
            Inspect and safely edit
            show database records.
          </p>
        </div>

        <div className="workspace-actions">
          <Button>Refresh</Button>

          <Button
                variant={editMode ? "primary" : "default"}
                onClick={() => setEditMode(!editMode)}
          >
                {editMode ? "Edit Mode On" : "Read Only"}
          </Button>

          <Button variant="primary">
            Export CSV
          </Button>
        </div>
      </div>

      <div className="database-layout">
        <Panel title="Tables">
          <div className="table-list">
            {Object.keys(tables).map(
              (table) => (
                <button
                  key={table}
                  className={`table-list-item ${
                    activeTable ===
                    table
                      ? "active"
                      : ""
                  }`}
                  onClick={() =>
                    setActiveTable(
                      table
                    )
                  }
                >
                  {table}
                </button>
              )
            )}
          </div>
        </Panel>

        <Panel
          title={activeTable}
          className="database-main-panel"
        >

            <div className="database-mode-banner">
              {modeLabel}
            </div>

            <input
              className="database-search"
              value={search}
              placeholder="Search rows..."
              onChange={(event) =>
                setSearch(event.target.value)
              }
            />

          

          {rows.length === 0 ? (
            <div className="empty-table-state">
              No rows in this table.
            </div>
          ) : (
            <table className="inventory-table">
              <thead>
                <tr>
                  {columns.map(
                    (column) => (
                      <th key={column}>
                        {column}
                      </th>
                    )
                  )}
                </tr>
              </thead>

              <tbody>
                {rows.map(
                  (row, index) => (
                    <tr key={index}>
                      {columns.map(
                        (column) => (
                          <td
                            key={
                              column
                            }
                          >
                            {
                              row[
                                column
                              ]
                            }
                          </td>
                        )
                      )}
                    </tr>
                  )
                )}
              </tbody>
            </table>
          )}
        </Panel>
      </div>
    </div>
  );
}