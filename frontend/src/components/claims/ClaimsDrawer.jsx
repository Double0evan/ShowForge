import { useEffect, useState } from "react";

import Badge from "../shared/Badge";
import Button from "../shared/Button";

function statusTone(status) {
  if (status === "Active")   return "success";
  if (status === "Removed")  return "danger";
  return "accent";
}

export default function ClaimsDrawer({ claim, onClose, onSetAuction, onRemoveRefund }) {
  const [editingAuction, setEditingAuction] = useState(false);
  const [auctionDraft, setAuctionDraft]     = useState("");
  const [saving, setSaving]                 = useState(false);
  const [removing, setRemoving]             = useState(false);

  useEffect(() => {
    setEditingAuction(false);
    setAuctionDraft(claim?.auctionNumber || "");
  }, [claim]);

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!claim) return null;

  const isActive  = claim.status === "Active";
  const isBin     = claim.sourceKey === "bin";

  async function handleSaveAuction() {
    setSaving(true);
    try {
      await onSetAuction?.(claim.itemCode, auctionDraft.trim());
      setEditingAuction(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleRemoveRefund() {
    if (!window.confirm(`Remove claim on ${claim.itemCode} and refund credit?`)) return;
    setRemoving(true);
    try {
      await onRemoveRefund?.(claim.itemCode, true);
      onClose();
    } finally {
      setRemoving(false);
    }
  }

  async function handleRemoveNoRefund() {
    if (!window.confirm(`Remove claim on ${claim.itemCode} WITHOUT refunding credit?`)) return;
    setRemoving(true);
    try {
      await onRemoveRefund?.(claim.itemCode, false);
      onClose();
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div className="drawer-layer">
      <button
        type="button"
        className="drawer-backdrop"
        onClick={onClose}
        aria-label="Close drawer"
      />

      <aside className="inventory-drawer claims-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <h2>{claim.itemCode}</h2>
            <Badge tone={statusTone(claim.status)}>{claim.status}</Badge>
            <Badge tone={isBin ? "accent" : "default"} style={{ marginLeft: 8 }}>
              {claim.source}
            </Badge>
          </div>
          <button type="button" className="drawer-close" onClick={onClose}>×</button>
        </div>

        {/* Preview image */}
        {claim.image && (
          <div className="drawer-preview">
            <img src={claim.image} alt={claim.itemCode} />
          </div>
        )}

        {/* Claim info */}
        <div className="drawer-meta-grid">
          <div className="drawer-section">
            <label>Claim ID</label>
            <strong>#{claim.id}</strong>
          </div>
          <div className="drawer-section">
            <label>Owner</label>
            <strong>{claim.owner}</strong>
          </div>
          <div className="drawer-section">
            <label>Rating</label>
            <strong>{claim.rating}</strong>
          </div>
          <div className="drawer-section">
            <label>Claimed At</label>
            <strong>{claim.createdAt?.slice(0, 16).replace("T", " ") || "—"}</strong>
          </div>
        </div>

        {/* Auction number — only editable field */}
        <div className="drawer-section">
          <label>Auction #</label>
          {editingAuction ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
              <input
                className="drawer-input"
                placeholder="e.g. 42"
                value={auctionDraft}
                onChange={(e) => setAuctionDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSaveAuction()}
                autoFocus
              />
              <Button variant="primary" onClick={handleSaveAuction} disabled={saving}>
                {saving ? "..." : "Save"}
              </Button>
              <Button onClick={() => setEditingAuction(false)}>Cancel</Button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
              <strong>{claim.auctionNumber ? `#${claim.auctionNumber}` : "—"}</strong>
              {isActive && (
                <Button onClick={() => setEditingAuction(true)}>Edit</Button>
              )}
            </div>
          )}
        </div>

        {/* Remove actions — only show on active claims */}
        {isActive && (
          <div className="drawer-actions">
            <Button variant="danger" onClick={handleRemoveRefund} disabled={removing}>
              {removing ? "Removing..." : "Remove + Refund"}
            </Button>
            <Button onClick={handleRemoveNoRefund} disabled={removing}>
              Remove (No Refund)
            </Button>
          </div>
        )}
      </aside>
    </div>
  );
}
