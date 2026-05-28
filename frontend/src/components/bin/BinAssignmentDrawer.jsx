import { useEffect, useState } from "react";
import Button from "../shared/Button";
import Badge from "../shared/Badge";

export default function BinAssignmentDrawer({ row, onClose, onAssign, onDelete, onFindMatch }) {
  const [buyerName, setBuyerName]     = useState("");
  const [discordName, setDiscordName] = useState("");
  const [discordId, setDiscordId]     = useState("");
  const [matchScore, setMatchScore]   = useState(0);
  const [matching, setMatching]       = useState(false);
  const [saving, setSaving]           = useState(false);

  useEffect(() => {
    setBuyerName(row?.whatnotName || "");
    setDiscordName(row?.discordName || "");
    setDiscordId(row?.discordId || "");
    setMatchScore(row?.matchScore || 0);
    setSaving(false);
    setMatching(false);
  }, [row]);

  useEffect(() => {
    function handleKey(e) { if (e.key === "Escape") onClose(); }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  if (!row) return null;

  async function handleFindMatch() {
    if (!buyerName.trim()) return;
    setMatching(true);
    try {
      const match = await onFindMatch(buyerName.trim());
      if (match?.ok) {
        setDiscordName(match.discordName || "");
        setDiscordId(match.discordId || "");
        setMatchScore(match.score || 0);
      } else {
        // Still fill in what we got so host can correct it
        setDiscordName(match?.discordName || "");
        setDiscordId(match?.discordId || "");
        setMatchScore(match?.score || 0);
      }
    } finally {
      setMatching(false);
    }
  }

  async function handleAssign() {
    setSaving(true);
    try {
      await onAssign(row.id, {
        itemCode:    row.itemCode,
        whatnotName: buyerName.trim() || row.whatnotName,
        discordName: discordName.trim() || buyerName.trim() || row.whatnotName,
        discordId:   discordId.trim(),
      });
    } finally {
      setSaving(false);
    }
  }

  const matchPct = Math.round(matchScore * 100);
  const matchColor =
    matchPct >= 90 ? "var(--green)"
    : matchPct >= 75 ? "var(--amber)"
    : matchPct > 0 ? "var(--red)"
    : "var(--muted)";

  return (
    <div className="drawer-layer">
      <button className="drawer-backdrop" type="button" onClick={onClose} aria-label="Close" />
      <aside className="inventory-drawer assignment-drawer" onClick={(e) => e.stopPropagation()}>

        <div className="drawer-header">
          <div>
            <span style={{ fontSize: 12, color: "var(--muted)" }}>Item #{row.cardNumber}</span>
            <h2>{row.itemCode}</h2>
            <Badge tone={row.claimed ? "success" : "default"}>
              {row.claimed ? "Assigned" : "Unassigned"}
            </Badge>
          </div>
          <button className="drawer-close" type="button" onClick={onClose}>×</button>
        </div>

        {row.image && (
          <div className="drawer-preview">
            <img src={row.image} alt={row.itemCode} />
          </div>
        )}

        {/* Buyer name — what host types/pastes from Whatnot */}
        <div className="drawer-section">
          <label>Whatnot Buyer Name</label>
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <input
              className="drawer-input"
              value={buyerName}
              onChange={(e) => setBuyerName(e.target.value)}
              placeholder="Paste from Whatnot..."
              onKeyDown={(e) => e.key === "Enter" && handleFindMatch()}
            />
            <Button onClick={handleFindMatch} disabled={matching || !buyerName.trim()}>
              {matching ? "..." : "Match"}
            </Button>
          </div>
        </div>

        {/* Discord match result */}
        <div className="drawer-section">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <label>Discord User</label>
            {matchPct > 0 && (
              <span style={{ fontSize: 12, color: matchColor, fontWeight: 600 }}>
                {matchPct}% match
              </span>
            )}
          </div>
          <input
            className="drawer-input"
            value={discordName}
            onChange={(e) => setDiscordName(e.target.value)}
            placeholder="Discord display name..."
            style={{ marginTop: 4 }}
          />
        </div>

        <div className="drawer-section">
          <label>Discord ID <span style={{ color: "var(--muted)", fontWeight: 400 }}>(optional)</span></label>
          <input
            className="drawer-input"
            value={discordId}
            onChange={(e) => setDiscordId(e.target.value)}
            placeholder="Filled automatically when matched"
            style={{ marginTop: 4 }}
          />
        </div>

        <div className="drawer-actions">
          <Button
            variant="primary"
            onClick={handleAssign}
            disabled={saving || row.claimed || !discordName.trim()}
          >
            {saving ? "Assigning..." : row.claimed ? "Already Assigned" : "Assign Claim"}
          </Button>
          <Button variant="danger" onClick={() => onDelete(row.id)}>
            Remove Row
          </Button>
        </div>

      </aside>
    </div>
  );
}
