import Badge from "../shared/Badge";
import Button from "../shared/Button";

function statusTone(status) {
  if (status === "Active")  return "success";
  if (status === "Removed") return "danger";
  return "accent";
}

export default function ClaimsRow({ claim, selected, onToggle, onView, onRemoveRefund }) {
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
        <div className="claim-item-cell">
          {claim.image && (
            <div className="card-preview" style={{ width: 40, height: 40 }}>
              <img src={claim.image} alt={claim.itemCode} />
            </div>
          )}
          <strong>{claim.itemCode}</strong>
        </div>
      </td>

      <td>
        <div className="claim-user-cell">
          <strong>{claim.owner}</strong>
          <span style={{ fontSize: 11, color: "var(--muted)" }}>ID {claim.userId}</span>
        </div>
      </td>

      <td>
        <Badge tone={claim.sourceKey === "bin" ? "accent" : "default"}>
          {claim.source}
        </Badge>
      </td>

      <td className="mono-cell">
        {claim.auctionNumber ? `#${claim.auctionNumber}` : "—"}
      </td>

      <td>
        <Badge tone={statusTone(claim.status)}>{claim.status}</Badge>
      </td>

      <td style={{ fontSize: 12, color: "var(--muted)" }}>
        {claim.createdAt?.slice(0, 10) || "—"}
      </td>

      <td className="row-actions">
        <Button onClick={onView}>View</Button>
        {claim.status === "Active" && (
          <Button variant="danger" onClick={() => onRemoveRefund?.(claim.itemCode, true)}>
            Refund
          </Button>
        )}
      </td>
    </tr>
  );
}
