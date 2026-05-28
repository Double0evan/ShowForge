// Maps raw backend row shapes → normalized frontend shapes.
// Column names come from Core/schema.sql and the queries in ui.py / main.py.

export function mapBackendInventoryItem(row = {}) {
  return {
    code: row.item_code,
    status: normalizeInventoryStatus(row.status),
    postMode: row.post_mode || "claim",
    publishedAt: row.published_at || null,
    createdAt: row.created_at || "—",
    updated: row.updated_at || "—",
    // preview_url is injected by the backend GET /api/inventory query
    image: row.preview_url || null,
    // No owner on inventory rows — owner lives on claims
    owner: "—",
    raw: row,
  };
}

export function normalizeInventoryStatus(status = "") {
  const map = {
    available: "Available",
    claimed: "Claimed",
    removed: "Removed",
    claimed_removed: "Removed",
  };
  return map[String(status).toLowerCase()] || status || "Unknown";
}

export function mapBackendClaim(row = {}) {
  const rating = String(row.item_code || "").startsWith("N") ? "NSFW" : "SFW";
  return {
    id: row.id,
    itemCode: row.item_code,
    itemName: row.item_code,
    owner: row.user_display_name || "—",
    userId: row.user_id,
    internalUserId: row.user_id,
    source: normalizeSource(row.source),
    sourceKey: row.source || "",
    auctionNumber: row.auction_number || "",
    status: row.removed_at ? "Removed" : "Active",
    rating,
    createdAt: row.created_at || "—",
    removedAt: row.removed_at || null,
    removedReason: row.removed_reason || "",
    // preview_url injected by GET /api/claims
    image: row.preview_url || null,
    raw: row,
  };
}

export function normalizeSource(source = "") {
  const map = {
    bin: "Bin Show",
    staff: "Direct Assign",
    button: "Discord Claim",
    reaction: "Discord Claim",
  };
  return map[String(source).toLowerCase()] || source || "Unknown";
}

// Auction log rows — from GET /api/binshow/state rows[] or /ui/binshow/log
// Real columns: id, position, card_number, winner_name, discord_name, claimed, created_at
// plus item_code and preview_url injected by the backend
export function mapBackendAuctionRow(row = {}) {
  const cardNumber = Number(row.card_number || 0);
  const itemCode = row.item_code || (cardNumber ? `N${String(cardNumber).padStart(3, "0")}` : "—");
  const claimed = Boolean(row.claimed);
  const hasWinner = Boolean(row.winner_name || row.discord_name);

  return {
    id: row.id,
    position: row.position,
    cardNumber,
    itemCode,
    whatnotName: row.winner_name || "",
    discordName: row.discord_name || "",
    discordId: row.discord_id || "",
    status: claimed ? "Assigned" : hasWinner ? "Needs Review" : "Unassigned",
    claimed,
    createdAt: row.created_at || "—",
    image: row.preview_url || null,
    raw: row,
  };
}

// Pending sales from bin_queue.sqlite — columns: id, auction_number, username, detected_at, matched
export function mapBackendPendingSale(row = {}) {
  return {
    id: row.id,
    auctionNumber: row.auction_number,
    username: row.username,
    detectedAt: row.detected_at || "—",
    matched: Boolean(row.matched),
    raw: row,
  };
}

// Users — columns: id, kind, discord_user_id, display_name, normalized_name, created_at,
//                  balance (computed), claims (count), merge_candidate (computed)
export function mapBackendUser(row = {}) {
  return {
    id: row.id,
    displayName: row.display_name || "—",
    kind: row.kind || "unknown",
    discordUserId: row.discord_user_id || null,
    verified: row.kind === "discord" && Boolean(row.discord_user_id),
    balance: Number(row.balance || 0),
    cardsOwned: Number(row.cards_owned || row.claims || 0),
    claims: Number(row.claims || 0),
    mergeCandidate: row.merge_candidate || null,
    createdAt: row.created_at || "—",
    raw: row,
  };
}
