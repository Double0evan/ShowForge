import Button from "../shared/Button";
import Badge from "../shared/Badge";

export default function InventoryRow({
  item,
  selected,
  onToggle,
  onView,
  onPublish,
}) {
  const isPublished = Boolean(item.publishedAt);
  const isClaimed   = item.status === "Claimed";
  const isRemoved   = item.status === "Removed";

  return (
    <tr className={selected ? "selected-row" : ""}>
      <td>
        <input
          type="checkbox"
          className="row-checkbox"
          checked={selected}
          onChange={onToggle}
        />
      </td>

      <td>
        <div className="card-preview">
          {item.image
            ? <img src={item.image} alt={item.code} />
            : <span>🃏</span>
          }
        </div>
      </td>

      <td className="item-code">{item.code}</td>

      <td>
        <Badge
          tone={
            item.status === "Available" ? "success"
            : item.status === "Claimed"  ? "danger"
            : "accent"
          }
        >
          {item.status}
        </Badge>
        {isPublished && !isClaimed && (
          <Badge tone="default" style={{ marginLeft: 6 }}>Listed</Badge>
        )}
      </td>

      <td>{item.postMode === "display" ? "Display" : "—"}</td>

      <td style={{ fontSize: 12, color: "var(--muted)" }}>
        {item.updated ? item.updated.slice(0, 10) : "—"}
      </td>

      <td className="row-actions">
        <Button onClick={onView}>View</Button>
        {!isClaimed && !isRemoved && (
          <Button variant="primary" onClick={onPublish}>
            {isPublished ? "Republish" : "Publish"}
          </Button>
        )}
      </td>
    </tr>
  );
}
