import { useCallback, useEffect, useMemo, useState } from "react";
import { showforgeApi } from "../api/showforgeApi";
import { apiClient } from "../api/apiClient";

export function useBinManager({ showToast } = {}) {
  const [auctionRows, setAuctionRows] = useState([]);
  const [loading, setLoading]         = useState(true);
  const [search, setSearch]           = useState("");
  const [selectedRow, setSelectedRow] = useState(null);
  const [error, setError]             = useState("");
  const [inserting, setInserting]     = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setError("");
      const state = await showforgeApi.listBinManagerState();
      setAuctionRows(state.auctionRows || []);
    } catch (err) {
      const msg = err.message || "Unable to load auction log.";
      setError(msg);
      showToast?.(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const filteredRows = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return auctionRows;
    return auctionRows.filter((row) =>
      [row.itemCode, row.whatnotName, row.discordName, String(row.cardNumber)]
        .filter(Boolean).some((v) => v.toLowerCase().includes(q))
    );
  }, [auctionRows, search]);

  const stats = useMemo(() => ({
    total:      auctionRows.length,
    assigned:   auctionRows.filter((r) => r.claimed).length,
    unassigned: auctionRows.filter((r) => !r.claimed).length,
  }), [auctionRows]);

  async function findMatch(name) {
    if (!name?.trim()) return null;
    try { return await showforgeApi.findDiscordMatch(name.trim()); }
    catch (err) { showToast?.(err.message || "Match lookup failed."); return null; }
  }

  async function assignRow(rowId, updates) {
    try {
      await showforgeApi.assignAuctionRow(rowId, updates);
      showToast?.(`${updates.itemCode} assigned to ${updates.discordName || updates.whatnotName}.`);
      setSelectedRow(null);
      await reload();
    } catch (err) {
      showToast?.(err.message || "Assignment failed.");
      throw err;
    }
  }

  // Smart delete — differs based on whether row is assigned
  async function deleteRow(rowId) {
    const row = auctionRows.find((r) => r.id === rowId);
    const isAssigned = row?.claimed;
    const isPlaceholder = row?.cardNumber === 0;

    let removeClaim = false;
    const refund = false; // Bin shows don't use credits — never refund

    if (isPlaceholder) {
      if (!window.confirm("Remove this placeholder row? Auction numbers will be restamped.")) return;
    } else if (isAssigned) {
      const choice = window.confirm(
        `This row is assigned to ${row.discordName || row.whatnotName} (${row.itemCode}).\n\n` +
        `Removing it will also remove the claim on ${row.itemCode}.\n` +
        `Auction numbers will be restamped.\n\nContinue?`
      );
      if (!choice) return;
      removeClaim = true;
    } else {
      if (!window.confirm("Remove this unassigned row? Auction numbers will be restamped.")) return;
    }

    try {
      // Use fetch directly since apiClient.delete doesn't support query params easily
      const url = `/ui/binshow/log/${rowId}?remove_claim=${removeClaim}&refund=${refund}`;
      const res = await apiClient.delete(url);

      if (isAssigned && removeClaim) {
        if (res.claim_removed) {
          showToast?.(`Row removed. Claim on ${row.itemCode} cleared.`);
        } else if (res.claim_error) {
          showToast?.(`Row removed but claim removal failed: ${res.claim_error}`);
        } else {
          showToast?.("Row removed.");
        }
      } else {
        showToast?.("Row removed. Auction numbers restamped.");
      }

      setSelectedRow(null);
      await reload();
    } catch (err) {
      showToast?.(err.message || "Delete failed.");
    }
  }

  async function insertPlaceholder(afterId) {
    setInserting(afterId);
    try {
      await showforgeApi.insertPlaceholder(afterId);
      showToast?.("Placeholder inserted. Auction numbers restamped.");
      await reload();
    } catch (err) {
      showToast?.(err.message || "Insert failed.");
    } finally {
      setInserting(null);
    }
  }

  async function clearAuctionLog() {
    if (!window.confirm("Clear the full auction log? This cannot be undone.")) return;
    try {
      await showforgeApi.clearAuctionLog();
      showToast?.("Auction log cleared.");
      setSelectedRow(null);
      await reload();
    } catch (err) {
      showToast?.(err.message || "Clear failed.");
    }
  }

  return {
    auctionRows, loading, error,
    search, setSearch,
    filteredRows, stats,
    inserting,
    selectedRow, setSelectedRow,
    findMatch, assignRow, deleteRow, insertPlaceholder, clearAuctionLog, reload,
  };
}
