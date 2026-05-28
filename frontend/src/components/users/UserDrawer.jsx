import { useEffect, useState } from "react";
import Badge from "../shared/Badge";
import Button from "../shared/Button";

export default function UserDrawer({ user, onClose, onAward, onAwardBulk }) {
  const [amount, setAmount] = useState(1);
  const [awarding, setAwarding] = useState(false);

  useEffect(() => { setAmount(1); }, [user]);

  useEffect(() => {
    function handleKeyDown(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!user) return null;

  async function handleAward() {
    setAwarding(true);
    try { await onAward?.(user.id, amount); }
    finally { setAwarding(false); }
  }

  return (
    <div className="drawer-layer">
      <button className="drawer-backdrop" type="button" onClick={onClose} aria-label="Close" />
      <aside className="inventory-drawer user-drawer" onClick={(e) => e.stopPropagation()}>

        <div className="drawer-header">
          <div>
            <h2>{user.displayName}</h2>
            <Badge tone={user.kind === "discord" ? "success" : user.kind === "pending" ? "accent" : "default"}>
              {user.kind}
            </Badge>
            {user.verified && <Badge tone="success" style={{ marginLeft: 6 }}>Verified</Badge>}
          </div>
          <button className="drawer-close" type="button" onClick={onClose}>×</button>
        </div>

        <div className="drawer-meta-grid">
          <div className="drawer-section">
            <label>User ID</label>
            <strong>#{user.id}</strong>
          </div>
          <div className="drawer-section">
            <label>Discord ID</label>
            <strong style={{ fontSize: 12 }}>{user.discordUserId || "—"}</strong>
          </div>
          <div className="drawer-section">
            <label>Balance</label>
            <strong>{user.balance} credit{user.balance !== 1 ? "s" : ""}</strong>
          </div>
          <div className="drawer-section">
            <label>Cards Owned</label>
            <strong>{user.cardsOwned}</strong>
          </div>
          <div className="drawer-section">
            <label>Claims</label>
            <strong>{user.claims}</strong>
          </div>
          <div className="drawer-section">
            <label>Created</label>
            <strong>{user.createdAt?.slice(0, 10) || "—"}</strong>
          </div>
        </div>

        {user.mergeCandidate && (
          <div className="merge-review-box">
            <Badge tone="accent">Merge Candidate</Badge>
            <p>
              This pending/guest user may match Discord user <strong>{user.mergeCandidate}</strong>.
              Merge happens automatically when the Discord user verifies in the server.
            </p>
          </div>
        )}

        <div className="drawer-section">
          <label>Award Credits</label>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
            <input
              className="drawer-input"
              type="number"
              min={1}
              max={99}
              value={amount}
              onChange={(e) => setAmount(Math.max(1, parseInt(e.target.value) || 1))}
              style={{ width: 70 }}
            />
            <Button variant="primary" onClick={handleAward} disabled={awarding}>
              {awarding ? "Awarding..." : `Award +${amount}`}
            </Button>
          </div>
        </div>

      </aside>
    </div>
  );
}
