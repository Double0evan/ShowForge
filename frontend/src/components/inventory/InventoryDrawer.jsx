import { useEffect, useState } from "react";

import Button from "../shared/Button";
import Badge from "../shared/Badge";

export default function InventoryDrawer({ item, onClose, onPublish, onRepublish, onRemove, onAssign, showToast }) {
  const [assignName, setAssignName]   = useState("");
  const [assigning, setAssigning]     = useState(false);
  const [showAssign, setShowAssign]   = useState(false);
  const [removing, setRemoving]       = useState(false);
  const [publishing, setPublishing]   = useState(false);

  useEffect(() => {
    setAssignName("");
    setShowAssign(false);
  }, [item]);

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!item) return null;

  const isClaimed  = item.status === "Claimed";
  const isRemoved  = item.status === "Removed";
  const isPublished = Boolean(item.publishedAt);

  const statusTone =
    item.status === "Available" ? "success"
    : item.status === "Claimed" ? "danger"
    : "accent";

  async function handlePublish() {
    setPublishing(true);
    try {
      if (isPublished) {
        await onRepublish?.(item.code);
        showToast?.(`${item.code} republished to catalog.`);
      } else {
        await onPublish?.(item.code);
        showToast?.(`${item.code} published to catalog.`);
      }
    } catch (e) {
      showToast?.(`Publish failed: ${e.message}`);
    } finally {
      setPublishing(false);
    }
  }

  async function handleAssign() {
    if (!assignName.trim()) return;
    setAssigning(true);
    try {
      await onAssign?.(item.code, assignName.trim());
      showToast?.(`${item.code} assigned to ${assignName.trim()}.`);
      setShowAssign(false);
      setAssignName("");
    } catch (e) {
      showToast?.(`Assign failed: ${e.message}`);
    } finally {
      setAssigning(false);
    }
  }

  async function handleRemove() {
    if (!window.confirm(`Remove ${item.code}? This cannot be undone.`)) return;
    setRemoving(true);
    try {
      await onRemove?.(item.code);
      showToast?.(`${item.code} removed.`);
      onClose();
    } catch (e) {
      showToast?.(`Remove failed: ${e.message}`);
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

      <aside className="inventory-drawer" onClick={(e) => e.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <h2>{item.code}</h2>
            <Badge tone={statusTone}>{item.status}</Badge>
            {isPublished && !isClaimed && (
              <Badge tone="default" style={{ marginLeft: 8 }}>Listed</Badge>
            )}
          </div>
          <button type="button" className="drawer-close" onClick={onClose}>×</button>
        </div>

        {/* Preview image */}
        <div className="drawer-preview">
          {item.image
            ? <img src={item.image} alt={item.code} />
            : <span>🃏</span>
          }
        </div>

        {/* Item info */}
        <div className="drawer-meta-grid">
          <div className="drawer-section">
            <label>Item Code</label>
            <strong>{item.code}</strong>
          </div>
          <div className="drawer-section">
            <label>Post Mode</label>
            <strong>{item.postMode === "display" ? "Display Only" : "Claim"}</strong>
          </div>
          <div className="drawer-section">
            <label>Status</label>
            <strong>{item.status}</strong>
          </div>
          <div className="drawer-section">
            <label>Published</label>
            <strong>{isPublished ? item.publishedAt?.slice(0, 10) : "Not yet"}</strong>
          </div>
          <div className="drawer-section">
            <label>Created</label>
            <strong>{item.createdAt?.slice(0, 10) || "—"}</strong>
          </div>
          <div className="drawer-section">
            <label>Updated</label>
            <strong>{item.updated?.slice(0, 10) || "—"}</strong>
          </div>
        </div>

        {/* Assign owner panel */}
        {!isClaimed && !isRemoved && (
          <div className="drawer-section">
            {showAssign ? (
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  className="drawer-input"
                  placeholder="Discord display name..."
                  value={assignName}
                  onChange={(e) => setAssignName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAssign()}
                  autoFocus
                />
                <Button variant="primary" onClick={handleAssign} disabled={assigning}>
                  {assigning ? "..." : "Assign"}
                </Button>
                <Button onClick={() => { setShowAssign(false); setAssignName(""); }}>
                  Cancel
                </Button>
              </div>
            ) : (
              <Button onClick={() => setShowAssign(true)}>Assign to User</Button>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="drawer-actions">
          {!isClaimed && !isRemoved && (
            <Button variant="primary" onClick={handlePublish} disabled={publishing}>
              {publishing ? "Publishing..." : isPublished ? "Republish" : "Publish"}
            </Button>
          )}
          {!isRemoved && (
            <Button variant="danger" onClick={handleRemove} disabled={removing}>
              {removing ? "Removing..." : "Remove"}
            </Button>
          )}
        </div>
      </aside>
    </div>
  );
}
