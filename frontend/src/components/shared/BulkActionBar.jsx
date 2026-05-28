import Button from "./Button";

export default function BulkActionBar({
  selectedCount = 0,
  actions = [],
  onClear,
  contextLabel = "selected",
}) {
  if (!selectedCount) return null;

  return (
    <div className="bulk-action-bar" role="region" aria-label="Bulk actions">
      <div className="bulk-action-summary">
        <strong>{selectedCount}</strong>
        <span>{contextLabel}</span>
      </div>

      <div className="bulk-action-controls">
        {actions.map((action) => (
          <Button
            key={action.key || action.label}
            variant={action.variant || "default"}
            disabled={action.disabled}
            onClick={action.onClick}
          >
            {action.label}
          </Button>
        ))}

        <Button variant="danger" onClick={onClear}>Clear</Button>
      </div>
    </div>
  );
}
