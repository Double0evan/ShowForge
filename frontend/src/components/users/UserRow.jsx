import Badge from "../shared/Badge";
import Button from "../shared/Button";

function kindTone(user) {
  if (user.kind === "discord") return "success";
  if (user.kind === "pending") return "accent";
  return "default";
}

export default function UserRow({ user, selected, onToggle, onView, onAward }) {
  return (
    <tr className={selected ? "selected-row" : ""}>
      <td>
        <input type="checkbox" className="row-checkbox" checked={selected} onChange={onToggle} />
      </td>

      <td>
        <div className="user-cell-main">
          <div className="user-avatar">{user.displayName?.[0]?.toUpperCase() || "?"}</div>
          <div>
            <strong>{user.displayName}</strong>
            <span style={{ fontSize: 11, color: "var(--muted)" }}>#{user.id}</span>
          </div>
        </div>
      </td>

      <td><Badge tone={kindTone(user)}>{user.kind}</Badge></td>

      <td className="mono-cell" style={{ fontSize: 11 }}>{user.discordUserId || "—"}</td>
      <td className="mono-cell">{user.balance}</td>
      <td className="mono-cell">{user.cardsOwned}</td>

      <td>
        {user.mergeCandidate
          ? <Badge tone="accent">Merge Pending</Badge>
          : user.verified
          ? <Badge tone="success">Verified</Badge>
          : <Badge>Unverified</Badge>
        }
      </td>

      <td className="row-actions">
        <Button onClick={onView}>View</Button>
        <Button onClick={() => onAward?.(user.id, 1)}>+1 Credit</Button>
      </td>
    </tr>
  );
}
