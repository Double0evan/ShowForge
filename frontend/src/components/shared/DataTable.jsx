export default function DataTable({
  columns,
  rows,
  rowKey,
  renderRow,
  emptyLabel = "No rows found.",
  className = "",
  sortKey,
  sortDirection,
  onSort,
  footerLabel,
  pagination,
}) {
  function renderHeader(column) {
    if (!column.sortable) {
      return column.label;
    }

    const isActive = sortKey === column.key;
    const directionLabel = sortDirection === "asc" ? "Ascending" : "Descending";

    return (
      <button
        type="button"
        className={`table-sort-button ${isActive ? "active" : ""}`}
        onClick={() => onSort?.(column.key)}
        title={isActive ? directionLabel : "Sort column"}
      >
        <span>{column.label}</span>
        <em>{isActive ? (sortDirection === "asc" ? "↑" : "↓") : "↕"}</em>
      </button>
    );
  }

  return (
    <div className={`data-table-frame ${className}`}>
      <table className="inventory-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} className={column.headerClassName || ""}>
                {renderHeader(column)}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {rows.map((row, index) =>
            renderRow ? (
              renderRow(row)
            ) : (
              <tr key={rowKey ? rowKey(row) : index}>
                {columns.map((column) => (
                  <td key={column.key} className={column.className || ""}>
                    {column.render ? column.render(row) : row[column.key]}
                  </td>
                ))}
              </tr>
            )
          )}
        </tbody>
      </table>

      {rows.length === 0 && <div className="empty-table-state">{emptyLabel}</div>}

      {(footerLabel || pagination) && (
        <div className="data-table-footer">
          <span>{footerLabel}</span>

          {pagination && (
            <div className="table-pagination">
              <select
                value={pagination.pageSize}
                onChange={(event) => pagination.onPageSizeChange?.(event.target.value)}
                aria-label="Rows per page"
              >
                {[10, 25, 50].map((size) => (
                  <option key={size} value={size}>{size} / page</option>
                ))}
              </select>

              <button
                type="button"
                onClick={() => pagination.onPageChange?.(pagination.page - 1)}
                disabled={pagination.page <= 1}
              >
                Previous
              </button>

              <strong>
                Page {pagination.page} of {pagination.totalPages}
              </strong>

              <button
                type="button"
                onClick={() => pagination.onPageChange?.(pagination.page + 1)}
                disabled={pagination.page >= pagination.totalPages}
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
