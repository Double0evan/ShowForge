import { useCallback, useEffect, useMemo, useState } from "react";
import { showforgeApi } from "../api/showforgeApi";

const DEFAULT_PAGE_SIZE = 20;

export function useInventory({ showToast } = {}) {
  const [items, setItems]               = useState([]);
  const [loading, setLoading]           = useState(true);
  const [selectedCodes, setSelected]    = useState([]);
  const [search, setSearchRaw]          = useState("");
  const [statusFilter, setStatusRaw]    = useState("All");
  const [sortKey, setSortKey]           = useState("code");
  const [sortDirection, setSortDir]     = useState("asc");
  const [page, setPage]                 = useState(1);
  const [pageSize, setPageSizeRaw]      = useState(DEFAULT_PAGE_SIZE);

  const loadInventory = useCallback(async () => {
    setLoading(true);
    try {
      const next = await showforgeApi.listInventory();
      setItems(next);
    } catch (e) {
      showToast?.(`Failed to load inventory: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadInventory(); }, [loadInventory]);

  // ── Filtering ─────────────────────────────────────────────────────────────

  const filteredItems = useMemo(() => {
    const q = search.toLowerCase().trim();
    const visible = items.filter((item) => {
      const matchesSearch =
        !q ||
        item.code?.toLowerCase().includes(q) ||
        item.status?.toLowerCase().includes(q);
      const matchesStatus =
        statusFilter === "All" || item.status === statusFilter;
      return matchesSearch && matchesStatus;
    });

    return [...visible].sort((a, b) => {
      const av = String(a[sortKey] ?? "").toLowerCase();
      const bv = String(b[sortKey] ?? "").toLowerCase();
      if (av < bv) return sortDirection === "asc" ? -1 : 1;
      if (av > bv) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });
  }, [items, search, statusFilter, sortKey, sortDirection]);

  const filterOptions = useMemo(() => {
    const unique = (vals) =>
      ["All", ...Array.from(new Set(vals.filter(Boolean))).sort()].map((v) => ({
        value: v, label: v,
      }));
    return {
      statuses: unique(items.map((i) => i.status)),
    };
  }, [items]);

  const activeFilterCount = [
    search.trim(),
    statusFilter,
  ].filter((v) => v && v !== "All").length;

  // ── Pagination ────────────────────────────────────────────────────────────

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / pageSize));
  const safePage   = Math.min(page, totalPages);

  useEffect(() => {
    if (page !== safePage) setPage(safePage);
  }, [page, safePage]);

  const pagedItems = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return filteredItems.slice(start, start + pageSize);
  }, [filteredItems, pageSize, safePage]);

  // ── Selection ─────────────────────────────────────────────────────────────

  const allVisibleSelected =
    pagedItems.length > 0 &&
    pagedItems.every((item) => selectedCodes.includes(item.code));

  function toggleRow(code) {
    setSelected((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
  }

  function toggleAllVisible() {
    if (allVisibleSelected) {
      setSelected((prev) =>
        prev.filter((code) => !pagedItems.some((item) => item.code === code))
      );
      return;
    }
    setSelected((prev) => {
      const next = new Set(prev);
      pagedItems.forEach((item) => next.add(item.code));
      return Array.from(next);
    });
  }

  function clearSelection() { setSelected([]); }

  // ── Sort / filter setters ─────────────────────────────────────────────────

  function resetPage() { setPage(1); }

  function setSearch(v)       { setSearchRaw(v);  resetPage(); }
  function setStatusFilter(v) { setStatusRaw(v);  resetPage(); }
  function setPageSize(v)     { setPageSizeRaw(Number(v)); resetPage(); }

  function clearFilters() {
    setSearchRaw("");
    setStatusRaw("All");
    resetPage();
  }

  function changeSort(key) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  // ── Mutations ─────────────────────────────────────────────────────────────

  function mergeUpdated(updatedCodes, patch) {
    // Reload is the safest approach for live mode since backend is source of truth
    // For instant feedback we optimistically patch status
    if (patch) {
      setItems((prev) =>
        prev.map((item) =>
          updatedCodes.includes(item.code) ? { ...item, ...patch } : item
        )
      );
    }
  }

  async function publishItems(codes) {
    if (!codes.length) return;
    try {
      const result = await showforgeApi.publishInventoryItems(codes);
      showToast?.(`${result.published} item(s) sent to catalog.`);
      // Reload to get updated published_at from backend
      await loadInventory();
      setSelected((prev) => prev.filter((c) => !codes.includes(c)));
    } catch (e) {
      showToast?.(`Publish failed: ${e.message}`);
    }
  }

  async function republishItem(code) {
    try {
      await showforgeApi.republishItem(code);
      showToast?.(`${code} republished.`);
      await loadInventory();
    } catch (e) {
      showToast?.(`Republish failed: ${e.message}`);
    }
  }

  async function removeItems(codes) {
    if (!codes.length) return;
    try {
      const result = await showforgeApi.removeInventoryItems(codes);
      showToast?.(`${result.removed} item(s) removed.`);
      mergeUpdated(codes, { status: "Removed" });
      setSelected((prev) => prev.filter((c) => !codes.includes(c)));
    } catch (e) {
      showToast?.(`Remove failed: ${e.message}`);
    }
  }

  async function assignItem(code, displayName) {
    try {
      await showforgeApi.assignInventoryItem(code, displayName);
      showToast?.(`${code} assigned to ${displayName}.`);
      await loadInventory();
    } catch (e) {
      showToast?.(`Assign failed: ${e.message}`);
    }
  }

  return {
    items,
    filteredItems,
    pagedItems,
    loading,
    // filters
    search,         setSearch,
    statusFilter,   setStatusFilter,
    filterOptions,
    activeFilterCount,
    clearFilters,
    // sort
    sortKey, sortDirection, changeSort,
    // selection
    selectedCodes,
    allVisibleSelected,
    toggleRow,
    toggleAllVisible,
    clearSelection,
    // pagination
    page: safePage,
    pageSize,
    setPage,
    setPageSize,
    totalPages,
    // actions
    publishItems,
    republishItem,
    removeItems,
    assignItem,
    reload: loadInventory,
  };
}
