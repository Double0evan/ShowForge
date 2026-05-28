import Badge from "../shared/Badge";
import Button from "../shared/Button";

export default function BinManagerRow({ row, onOpen, onDelete, onInsertAfter, inserting }) {
  const matchPct      = Math.round((row.matchScore || 0) * 100);
  const isPlaceholder = row.whatnotName === "[placeholder]" || row.cardNumber === 0;

  return (
    <>
      <tr className={isPlaceholder ? "bin-placeholder-row" : ""}>

        {/* Auction # — prominent */}
        <td style={{ textAlign: "center" }}>
          <div style={{
            display: "inline-flex", flexDirection: "column", alignItems: "center",
            background: isPlaceholder ? "transparent" : "rgba(124,92,255,0.12)",
            border: isPlaceholder ? "none" : "1px solid rgba(124,92,255,0.25)",
            borderRadius: 8, padding: "4px 10px", minWidth: 48,
          }}>
            <span style={{ fontSize: 15, fontWeight: 800, color: isPlaceholder ? "var(--muted)" : "var(--accent, #7c6aff)", lineHeight: 1 }}>
              {row.position}
            </span>
            <span style={{ fontSize: 9, color: "var(--muted)", letterSpacing: "0.08em", marginTop: 2 }}>
              AUCTION
            </span>
          </div>
        </td>

        {/* Item */}
        <td>
          {isPlaceholder ? (
            <span style={{ color: "var(--muted)", fontStyle: "italic", fontSize: 13 }}>
              — other sale / cancellation —
            </span>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {row.image && (
                <div className="bin-card-thumb">
                  <img src={row.image} alt={row.itemCode} />
                </div>
              )}
              <div>
                <strong style={{ fontSize: 14 }}>{row.itemCode}</strong>
                <div style={{ fontSize: 11, color: "var(--muted)" }}>Card #{row.cardNumber}</div>
              </div>
            </div>
          )}
        </td>

        {/* Whatnot buyer */}
        <td>
          <strong>{isPlaceholder ? "—" : (row.whatnotName || "—")}</strong>
        </td>

        {/* Discord match */}
        <td>
          {!isPlaceholder && row.discordName ? (
            <div>
              <strong>{row.discordName}</strong>
              {matchPct > 0 && (
                <span style={{
                  marginLeft: 6, fontSize: 11,
                  color: matchPct >= 90 ? "var(--green)" : matchPct >= 75 ? "var(--amber)" : "var(--red)"
                }}>
                  {matchPct}%
                </span>
              )}
            </div>
          ) : (
            <span style={{ color: "var(--muted)" }}>
              {isPlaceholder ? "—" : "Unassigned"}
            </span>
          )}
        </td>

        {/* Status */}
        <td>
          {isPlaceholder
            ? <Badge tone="default">Skipped</Badge>
            : <Badge tone={row.claimed ? "success" : "default"}>{row.claimed ? "Assigned" : "Pending"}</Badge>
          }
        </td>

        {/* Actions */}
        <td className="row-actions">
          {!isPlaceholder && (
            <Button onClick={onOpen}>{row.claimed ? "View" : "Assign"}</Button>
          )}
          <Button variant="danger" onClick={() => onDelete(row.id)}>Remove</Button>
        </td>
      </tr>

      {/* Insert placeholder between rows */}
      <tr className="bin-insert-row">
        <td colSpan={6}>
          <div className="bin-insert-zone">
            <button
              type="button"
              className="bin-insert-btn"
              onClick={() => onInsertAfter(row.id)}
              disabled={inserting !== null}
              title="Insert other sale / cancellation here"
            >
              {inserting === row.id ? "Inserting..." : "+ Insert Skip"}
            </button>
          </div>
        </td>
      </tr>
    </>
  );
}
