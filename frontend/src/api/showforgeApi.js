import { mockInventory } from "../data/mockInventory";
import { mockClaims } from "../data/mockClaims";
import { mockAuctionRows, mockPendingSales } from "../data/mockBinQueue";
import { mockUsers } from "../data/mockUsers";

import { isMockMode } from "./config";
import { liveShowforgeApi } from "./liveShowforgeApi";
import { activityLog } from "./activityLog";
import { liveCapabilities } from "./backendContracts";

const MOCK_DELAY = 220;

function wait(ms = MOCK_DELAY) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function nowLabel() {
  return new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function clone(value) {
  return structuredClone ? structuredClone(value) : JSON.parse(JSON.stringify(value));
}

function pushActivity(type, title, detail) {
  activityLog.push({ type, title, detail });
}

function createMockApi() {
  let inventory = clone(mockInventory);
  let claims = clone(mockClaims);
  let auctionRows = clone(mockAuctionRows);
  let pendingSales = clone(mockPendingSales);
  let users = clone(mockUsers);

  return {
    mode: "mock",
    capabilities: {
      ...liveCapabilities,
      claims: { ...liveCapabilities.claims, mockStatusOnly: true },
      binManager: { ...liveCapabilities.binManager, manualReviewStatus: true },
      users: { ...liveCapabilities.users, merge: true },
    },

    async getSystemState() {
      await wait(80);

      return {
        mode: "mock",
        capabilities: {
          ...liveCapabilities,
          claims: { ...liveCapabilities.claims, mockStatusOnly: true },
          binManager: { ...liveCapabilities.binManager, manualReviewStatus: true },
          users: { ...liveCapabilities.users, merge: true },
        },
        activeShow: "May_7_Live",
        backend: "deferred",
        watcher: { running: true, processing: true },
        counts: {
          inventory: inventory.length,
          claims: claims.length,
          auctionRows: auctionRows.length,
          users: users.length,
        },
      };
    },

    async listActivity() {
      await wait(80);
      return activityLog.list();
    },

    subscribeActivity(listener) {
      return activityLog.subscribe(listener);
    },

    async listInventory() {
      await wait();
      return clone(inventory);
    },

    async updateInventoryItem(code, updates) {
      await wait();

      inventory = inventory.map((item) =>
        item.code === code
          ? {
              ...item,
              ...updates,
              updated: nowLabel(),
            }
          : item
      );

      const updated = inventory.find((item) => item.code === code);
      pushActivity("inventory", `${code} updated`, "Inventory drawer saved mock changes.");
      return clone(updated);
    },

    async publishInventoryItems(codes) {
      await wait();

      const codeSet = new Set(codes);
      inventory = inventory.map((item) =>
        codeSet.has(item.code)
          ? {
              ...item,
              status: "Catalog",
              updated: nowLabel(),
            }
          : item
      );

      pushActivity("inventory", `${codes.length} item(s) published`, "Mock catalog publish completed.");

      return {
        published: codes.length,
        items: clone(inventory.filter((item) => codeSet.has(item.code))),
      };
    },

    async updateInventoryStatus(codes, status) {
      await wait();

      const codeSet = new Set(codes);
      inventory = inventory.map((item) =>
        codeSet.has(item.code)
          ? {
              ...item,
              status,
              owner: status === "Available" ? "—" : item.owner,
              updated: nowLabel(),
            }
          : item
      );

      pushActivity("inventory", `${codes.length} item(s) marked ${status}`, "Mock status update applied.");

      return {
        updated: codes.length,
        items: clone(inventory.filter((item) => codeSet.has(item.code))),
      };
    },

    async removeInventoryItems(codes) {
      await wait();

      const codeSet = new Set(codes);
      inventory = inventory.map((item) =>
        codeSet.has(item.code)
          ? {
              ...item,
              status: "Removed",
              updated: nowLabel(),
            }
          : item
      );

      pushActivity("inventory", `${codes.length} item(s) removed`, "Mock removal staged.");

      return {
        removed: codes.length,
        items: clone(inventory.filter((item) => codeSet.has(item.code))),
      };
    },

    async listClaims() {
      await wait();
      return clone(claims);
    },

    async updateClaim(id, updates) {
      await wait();

      claims = claims.map((claim) =>
        claim.id === id
          ? {
              ...claim,
              ...updates,
              updatedAt: "just now",
            }
          : claim
      );

      const updated = claims.find((claim) => claim.id === id);
      pushActivity("claims", `${updated?.itemCode || "Claim"} updated`, "Claim ledger mock record changed.");
      return clone(updated);
    },

    async updateClaimsStatus(ids, status) {
      await wait();

      const idSet = new Set(ids);
      claims = claims.map((claim) =>
        idSet.has(claim.id)
          ? {
              ...claim,
              status,
              updatedAt: "just now",
            }
          : claim
      );

      pushActivity("claims", `${ids.length} claim(s) marked ${status}`, "Claim ledger mock status update.");

      return {
        updated: ids.length,
        claims: clone(claims.filter((claim) => idSet.has(claim.id))),
      };
    },

    async postClaimSummary(rating) {
      await wait();
      pushActivity("claims", `${String(rating).toUpperCase()} summary queued`, "Mock claim summary action completed.");
      return { ok: true, rating };
    },

    async refundClaims(ids) {
      await wait();

      const idSet = new Set(ids);
      claims = claims.map((claim) =>
        idSet.has(claim.id)
          ? {
              ...claim,
              status: "Refunded",
              updatedAt: "just now",
              notes: claim.notes
                ? `${claim.notes} Refund staged in mock state.`
                : "Refund staged in mock state.",
            }
          : claim
      );

      pushActivity("claims", `${ids.length} claim refund(s) staged`, "Refund action is mocked until backend wiring.");

      return {
        refunded: ids.length,
        claims: clone(claims.filter((claim) => idSet.has(claim.id))),
      };
    },

    async listBinManagerState() {
      await wait();

      return {
        auctionRows: clone(auctionRows),
        pendingSales: clone(pendingSales),
        watcher: { running: true, processing: true, lastEvent: "auction log synced" },
      };
    },

    async findDiscordMatch(whatnotName) {
      await wait(120);
      const matchName = String(whatnotName || "").trim();
      return {
        ok: Boolean(matchName),
        discordName: matchName,
        discordId: "",
        score: matchName ? 0.88 : 0,
      };
    },

    async assignAuctionRow(rowId, updates) {
      await wait();

      auctionRows = auctionRows.map((row) =>
        row.id === rowId
          ? {
              ...row,
              ...updates,
              status: "Assigned",
              claimed: true,
              matchScore: updates.matchScore ?? row.matchScore ?? 1,
            }
          : row
      );

      const updated = auctionRows.find((row) => row.id === rowId);
      pushActivity("bin", `${updated?.itemCode || "Auction row"} assigned`, `${updated?.discordName || updated?.whatnotName || "Winner"} linked in mock queue.`);
      return clone(updated);
    },

    async setAuctionRowStatus(rowId, status) {
      await wait();

      auctionRows = auctionRows.map((row) =>
        row.id === rowId ? { ...row, status } : row
      );

      const updated = auctionRows.find((row) => row.id === rowId);
      pushActivity("bin", `${updated?.itemCode || "Auction row"} marked ${status}`, "Bin Manager mock status update.");
      return clone(updated);
    },

    async deleteAuctionRow(rowId) {
      await wait();

      auctionRows = auctionRows
        .filter((row) => row.id !== rowId)
        .map((row, index) => ({ ...row, position: index + 1 }));

      pushActivity("bin", "Auction row removed", "Auction positions restamped in mock queue.");

      return { ok: true, deleted: rowId, auctionRows: clone(auctionRows) };
    },

    async clearAuctionLog() {
      await wait();
      const cleared = auctionRows.length;
      auctionRows = [];
      pushActivity("bin", "Auction log cleared", "Mock auction log cleared.");
      return { ok: true, cleared, auctionRows: [] };
    },

    async listUsers() {
      await wait();
      return clone(users);
    },

    async updateUser(id, updates) {
      await wait();

      users = users.map((user) =>
        user.id === id
          ? {
              ...user,
              ...updates,
              lastSeen: "just now",
            }
          : user
      );

      const updated = users.find((user) => user.id === id);
      pushActivity("users", `${updated?.displayName || "User"} updated`, "User mock profile saved.");
      return clone(updated);
    },

    async adjustUserCredits(ids, amount) {
      await wait();

      const idSet = new Set(ids);
      users = users.map((user) =>
        idSet.has(user.id)
          ? {
              ...user,
              balance: Number(user.balance || 0) + Number(amount || 0),
              lastSeen: "just now",
            }
          : user
      );

      pushActivity("users", `${ids.length} user balance(s) adjusted`, `${amount > 0 ? "+" : ""}${amount} credit(s) in mock ledger.`);

      return {
        updated: ids.length,
        users: clone(users.filter((user) => idSet.has(user.id))),
      };
    },

    async mergeUser(id) {
      await wait();

      users = users.map((user) =>
        user.id === id
          ? {
              ...user,
              kind: "discord",
              verified: true,
              discordUserId: user.discordUserId || `mock-discord-${id}`,
              mergeCandidate: null,
              lastSeen: "just now",
              notes: user.notes
                ? `${user.notes} Mock merge completed.`
                : "Mock merge completed.",
            }
          : user
      );

      const updated = users.find((user) => user.id === id);
      pushActivity("users", `${updated?.displayName || "User"} merged`, "Pending/guest merge completed in mock state.");
      return clone(updated);
    },

    async addGuestUser(displayName) {
      await wait();

      const created = {
        id: Math.max(0, ...users.map((user) => user.id)) + 1,
        displayName,
        kind: "guest",
        discordUserId: null,
        verified: false,
        balance: 0,
        cardsOwned: 0,
        claims: 0,
        trades: 0,
        mergeCandidate: null,
        lastSeen: "just now",
        notes: "Created from React mock user workspace.",
      };

      users = [created, ...users];
      pushActivity("users", `${displayName} added`, "Guest user created in mock state.");
      return clone(created);
    },

    async queueInventoryUpload(queuedFiles) {
      await wait(520);

      pushActivity("uploads", `${queuedFiles.length} file(s) queued`, "Upload workflow passed validation and staged files.");

      return {
        queued: queuedFiles.length,
        files: queuedFiles.map((file, index) => ({
          id: file.id,
          uploadId: `mock-upload-${Date.now()}-${index}`,
          filename: file.filename,
          rating: file.rating,
          status: "Queued",
        })),
      };
    },
  };
}

const mockApi = createMockApi();

export const showforgeApi = isMockMode() ? mockApi : liveShowforgeApi;
