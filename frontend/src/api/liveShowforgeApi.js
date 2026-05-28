import { apiClient } from "./apiClient";
import { endpoints } from "./endpoints";
import { liveCapabilities } from "./backendContracts";
import {
  mapBackendAuctionRow,
  mapBackendClaim,
  mapBackendInventoryItem,
  mapBackendPendingSale,
  mapBackendUser,
} from "./mappers";

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

export const liveShowforgeApi = {
  mode: "live",
  capabilities: liveCapabilities,

  // ── System state ──────────────────────────────────────────────────────────

  async getSystemState() {
    const [health, inventoryRes, claimsRes, usersRes, binRes] = await Promise.allSettled([
      apiClient.get(endpoints.health),
      this.listInventory(),
      this.listClaims(),
      this.listUsers(),
      this.listBinManagerState(),
    ]);

    const activeShow = health.value?.active_show || null;

    return {
      mode: "live",
      capabilities: liveCapabilities,
      activeShow,
      backend: health.status === "fulfilled" ? "connected" : "unreachable",
      watcher: binRes.value?.watcher || { running: false, processing: false, lastEvent: "unknown" },
      counts: {
        inventory: inventoryRes.value?.length || 0,
        claims: claimsRes.value?.length || 0,
        auctionRows: binRes.value?.auctionRows?.length || 0,
        users: usersRes.value?.length || 0,
      },
    };
  },

  // Activity feed is not a real-time endpoint yet — returns empty list in live mode.
  async listActivity() {
    return [];
  },
  subscribeActivity() {
    return () => {};
  },

  // ── Inventory ─────────────────────────────────────────────────────────────

  async listInventory() {
    const response = await apiClient.get(endpoints.inventory.list);
    return safeArray(response.items).map(mapBackendInventoryItem);
  },

  async publishInventoryItems(codes) {
    const results = [];
    for (const itemCode of codes) {
      const fd = apiClient.toFormData({ item_code: itemCode });
      results.push(await apiClient.post(endpoints.inventory.publish, fd));
    }
    const published = results.filter((r) => r.ok !== false).length;
    return { published, items: [] };
  },

  async republishItem(itemCode) {
    const fd = apiClient.toFormData({ item_code: itemCode });
    return apiClient.post(endpoints.inventory.republish, fd);
  },

  async removeInventoryItems(codes) {
    const results = [];
    for (const itemCode of codes) {
      const fd = apiClient.toFormData({ item_code: itemCode });
      results.push(await apiClient.post(endpoints.inventory.remove, fd));
    }
    const removed = results.filter((r) => r.ok !== false).length;
    return { removed, items: [] };
  },

  async assignInventoryItem(itemCode, displayName) {
    const fd = apiClient.toFormData({ item_code: itemCode, display_name: displayName });
    return apiClient.post(endpoints.inventory.assign, fd);
  },

  // updateInventoryItem — no backend endpoint for editing metadata, reload after action
  async updateInventoryItem() {
    throw new Error("Item metadata editing is not supported in live mode.");
  },

  // updateInventoryStatus — no generic status-flip endpoint; use publish/remove/assign
  async updateInventoryStatus() {
    throw new Error("Use publishInventoryItems, removeInventoryItems, or assignInventoryItem instead.");
  },

  // Upload files to inbox — backend watermarks + uploads to Discord
  async queueInventoryUpload(queuedFiles) {
    const byRating = queuedFiles.reduce((acc, item) => {
      acc[item.rating] = acc[item.rating] || [];
      acc[item.rating].push(item.file);
      return acc;
    }, {});

    const results = [];
    for (const [rating, files] of Object.entries(byRating)) {
      const fd = new FormData();
      fd.append("rating", rating);
      for (const file of files) {
        fd.append("files", file);
      }
      results.push(await apiClient.post(endpoints.inventory.upload, fd));
    }
    return { queued: queuedFiles.length, results };
  },

  // Poll for lightweight status updates (published_at, status changes)
  async pollInventory() {
    return apiClient.get(endpoints.inventory.poll);
  },

  // ── Claims ────────────────────────────────────────────────────────────────

  async listClaims(includeRemoved = false) {
    const response = await apiClient.get(
      `${endpoints.claims.list}${includeRemoved ? "?include_removed=true" : ""}`
    );
    return safeArray(response.claims).map(mapBackendClaim);
  },

  async removeClaim(itemCode, refund = true) {
    const fd = apiClient.toFormData({
      item_code: itemCode,
      refund: refund ? "true" : "false",
    });
    return apiClient.post(endpoints.claims.remove, fd);
  },

  async setClaimAuctionNumber(itemCode, auctionNumber) {
    const fd = apiClient.toFormData({ item_code: itemCode, auction_number: String(auctionNumber) });
    return apiClient.post(endpoints.claims.setAuction, fd);
  },

  async postClaimSummary(rating) {
    const fd = apiClient.toFormData({ rating });
    return apiClient.post(endpoints.claims.summary, fd);
  },

  // Kept for compatibility with hooks that call this
  async updateClaim(id, updates = {}) {
    if (Object.prototype.hasOwnProperty.call(updates, "auctionNumber")) {
      const itemCode = updates.itemCode || updates.item_code || String(id);
      return this.setClaimAuctionNumber(itemCode, updates.auctionNumber);
    }
    throw new Error("Only auction number correction is supported in live mode.");
  },

  async updateClaimsStatus() {
    throw new Error("Claims do not have manual statuses — use removeClaim instead.");
  },

  async refundClaims(itemCodes) {
    const results = [];
    for (const itemCode of itemCodes) {
      results.push(await this.removeClaim(String(itemCode), true));
    }
    return { refunded: results.filter((r) => r.ok !== false).length, results };
  },

  // ── Bin Manager ───────────────────────────────────────────────────────────

  async listBinManagerState() {
    const response = await apiClient.get(endpoints.binManager.state);

    const auctionRows = safeArray(response.rows).map(mapBackendAuctionRow);
    const pendingSales = safeArray(response.pending_sales).map(mapBackendPendingSale);

    return {
      auctionRows,
      pendingSales,
      watcher: response.watcher || { running: false, processing: false, lastEvent: "unknown" },
    };
  },

  async findDiscordMatch(whatnotName) {
    if (!whatnotName?.trim()) return { ok: false, match: null, score: 0 };
    const response = await apiClient.get(
      `${endpoints.binManager.fuzzy}?whatnot_name=${encodeURIComponent(whatnotName.trim())}`
    );
    return {
      ok: Boolean(response.ok),
      discordName: response.match || "",
      discordId: response.discord_id || "",
      score: Number(response.score || 0),
      raw: response,
    };
  },

  // Submit a bin show auction assignment (the main bin show workflow)
  async submitBinAssignment({ auctionNumber, whatnotName, discordName, discordId = "" }) {
    const fd = apiClient.toFormData({
      auction_number: String(auctionNumber),
      whatnot_name: whatnotName,
      discord_name: discordName,
      discord_id: discordId,
    });
    return apiClient.post(endpoints.binManager.submit, fd);
  },

  // Assign via auction log entry
  async assignAuctionRow(rowId, updates = {}) {
    const fd = apiClient.toFormData({
      whatnot_name: updates.whatnotName || updates.whatnot_name || "",
      discord_name: updates.discordName || updates.discord_name || "",
      discord_id: updates.discordId || updates.discord_id || "",
    });
    return apiClient.post(endpoints.binManager.logAssign(rowId), fd);
  },

  async insertPlaceholder(afterId) {
    const fd = apiClient.toFormData(afterId != null ? { after_id: String(afterId) } : {});
    return apiClient.post(endpoints.binManager.logInsert, fd);
  },

  async deleteAuctionRow(rowId) {
    return apiClient.delete(endpoints.binManager.logDelete(rowId));
  },

  async clearAuctionLog() {
    return apiClient.post(endpoints.binManager.logClear, new FormData());
  },

  // setAuctionRowStatus — no backend equivalent, not supported
  async setAuctionRowStatus() {
    throw new Error("Auction row status is determined by the claim, not a manual flag.");
  },

  async listPendingReviews() {
    return apiClient.get(endpoints.binManager.reviews);
  },

  async resolveReview(reviewId, discordDisplayName) {
    return apiClient.post(
      `${endpoints.binManager.reviewReassign(reviewId)}?discord_display_name=${encodeURIComponent(discordDisplayName)}`
    );
  },

  async keepGuestReview(reviewId) {
    return apiClient.post(endpoints.binManager.reviewKeepGuest(reviewId));
  },

  // ── Users ─────────────────────────────────────────────────────────────────

  async listUsers() {
    const response = await apiClient.get(endpoints.users.list);
    return safeArray(response.users).map(mapBackendUser);
  },

  async adjustUserCredits(userIds, amount) {
    const results = [];
    for (const userId of userIds) {
      const fd = apiClient.toFormData({
        user_id: String(userId),
        delta: String(amount),
        note: "Adjusted from React admin",
      });
      results.push(await apiClient.post(endpoints.users.adjust, fd));
    }
    return { updated: results.filter((r) => r.ok !== false).length, results };
  },

  async awardBulkCredits(userIds, amount, note = "") {
    const fd = apiClient.toFormData({
      user_ids: userIds.join(","),
      amount: String(amount),
      note,
    });
    return apiClient.post(endpoints.users.awardBulk, fd);
  },

  async addGuestUser(displayName) {
    const fd = apiClient.toFormData({ command: `add_guest "${displayName}"` });
    return apiClient.post(endpoints.users.consoleRun, fd);
  },

  async searchMembers(q = "") {
    return apiClient.get(`${endpoints.users.membersSearch}?q=${encodeURIComponent(q)}`);
  },

  // updateUser — no generic profile edit endpoint
  async updateUser() {
    throw new Error("User profile editing is not available in live mode.");
  },

  // mergeUser — auto-merge happens server-side on upsert_discord; no manual trigger yet
  async mergeUser() {
    throw new Error("Merge happens automatically when the Discord user verifies. No manual trigger yet.");
  },

  // ── Console ───────────────────────────────────────────────────────────────

  async runConsoleCommand(command) {
    const fd = apiClient.toFormData({ command });
    return apiClient.post(endpoints.users.consoleRun, fd);
  },

  async getConsoleContext() {
    return apiClient.get(endpoints.users.consoleContext);
  },

  // ── Show control ──────────────────────────────────────────────────────────

  async getActiveShow() {
    return apiClient.get(endpoints.show.active);
  },

  async getShowMode() {
    return apiClient.get(endpoints.show.mode);
  },

  async setShowMode(mode) {
    return apiClient.post(`${endpoints.show.mode}?mode=${mode}`);
  },

  async newShow(date, name) {
    const fd = apiClient.toFormData({ date, name });
    return apiClient.post(endpoints.show.new, fd);
  },

  async endShow() {
    return apiClient.post(endpoints.show.end);
  },

  async resetClaims() {
    return apiClient.post(endpoints.show.resetClaims);
  },

  // ── Watcher ───────────────────────────────────────────────────────────────

  async getWatcherLog(lines = 200) {
    return apiClient.get(`${endpoints.watcher.log}?lines=${lines}`);
  },

  async startWatcher() {
    return apiClient.post(endpoints.watcher.start);
  },

  async stopWatcher() {
    return apiClient.post(endpoints.watcher.stop);
  },

  async clearWatcherLog() {
    return apiClient.post(endpoints.watcher.clear);
  },

  // ── Trade ─────────────────────────────────────────────────────────────────

  async lockTrade() {
    return apiClient.post(endpoints.trade.lock);
  },
  async unlockTrade() {
    return apiClient.post(endpoints.trade.unlock);
  },
  async refreshAllTrades() {
    return apiClient.post(endpoints.trade.refreshAll);
  },
  async closeTradeChannels() {
    return apiClient.post(endpoints.trade.closeChannels);
  },

  // ── Native pickers ────────────────────────────────────────────────────────

  async pickFolder() {
    return apiClient.get(endpoints.pick.folder);
  },

  async pickFile(accept = "") {
    return apiClient.get(`${endpoints.pick.file}?accept=${encodeURIComponent(accept)}`);
  },
};
