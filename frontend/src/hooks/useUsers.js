import { useCallback, useEffect, useMemo, useState } from "react";
import { showforgeApi } from "../api/showforgeApi";

export function useUsers({ showToast } = {}) {
  const [users, setUsers]          = useState([]);
  const [loading, setLoading]      = useState(true);
  const [search, setSearch]        = useState("");
  const [kindFilter, setKindFilter]     = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");
  const [selectedIds, setSelectedIds]   = useState([]);
  const [sortKey, setSortKey]           = useState("displayName");
  const [sortDirection, setSortDir]     = useState("asc");
  const [page, setPage]                 = useState(1);
  const [pageSize, setPageSizeRaw]      = useState(20);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setUsers(await showforgeApi.listUsers());
    } catch (e) {
      showToast?.(`Failed to load users: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = users.filter((u) => {
      const matchesSearch = !q || [u.displayName, u.discordUserId, u.kind, u.id]
        .filter(Boolean).some((v) => String(v).toLowerCase().includes(q));
      const matchesKind   = kindFilter === "All" || u.kind === kindFilter;
      const matchesStatus =
        statusFilter === "All" ||
        (statusFilter === "Verified"     && u.verified) ||
        (statusFilter === "Unverified"   && !u.verified) ||
        (statusFilter === "Merge Review" && Boolean(u.mergeCandidate));
      return matchesSearch && matchesKind && matchesStatus;
    });
    rows.sort((a, b) => {
      const r = String(a[sortKey] ?? "").localeCompare(String(b[sortKey] ?? ""), undefined, { numeric: true });
      return sortDirection === "asc" ? r : -r;
    });
    return rows;
  }, [users, search, kindFilter, statusFilter, sortKey, sortDirection]);

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / pageSize));
  const safePage   = Math.min(page, totalPages);

  const pagedUsers = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return filteredUsers.slice(start, start + pageSize);
  }, [filteredUsers, safePage, pageSize]);

  const allVisibleSelected =
    pagedUsers.length > 0 && pagedUsers.every((u) => selectedIds.includes(u.id));

  const stats = useMemo(() => ({
    total:       users.length,
    verified:    users.filter((u) => u.verified).length,
    pending:     users.filter((u) => u.kind === "pending").length,
    mergeReview: users.filter((u) => u.mergeCandidate).length,
    credits:     users.reduce((sum, u) => sum + Number(u.balance || 0), 0),
  }), [users]);

  const filterOptions = useMemo(() => ({
    kinds:    ["All", ...Array.from(new Set(users.map((u) => u.kind)))].map((v) => ({ value: v, label: v })),
    statuses: ["All", "Verified", "Unverified", "Merge Review"].map((v) => ({ value: v, label: v })),
  }), [users]);

  const activeFilterCount = [search, kindFilter !== "All", statusFilter !== "All"].filter(Boolean).length;

  function setPageSize(v) { setPageSizeRaw(Number(v)); setPage(1); }
  function clearFilters()  { setSearch(""); setKindFilter("All"); setStatusFilter("All"); setPage(1); }
  function clearSelection(){ setSelectedIds([]); }

  function toggleRow(id) {
    setSelectedIds((p) => p.includes(id) ? p.filter((x) => x !== id) : [...p, id]);
  }
  function toggleAllVisible() {
    if (allVisibleSelected) {
      setSelectedIds((p) => p.filter((id) => !pagedUsers.some((u) => u.id === id)));
    } else {
      setSelectedIds((p) => Array.from(new Set([...p, ...pagedUsers.map((u) => u.id)])));
    }
  }
  function changeSort(key) {
    if (sortKey === key) { setSortDir((d) => d === "asc" ? "desc" : "asc"); }
    else { setSortKey(key); setSortDir("asc"); }
  }

  async function awardCredits(ids, amount = 1) {
    const list = Array.isArray(ids) ? ids : [ids];
    try {
      await showforgeApi.awardBulkCredits(list, amount);
      showToast?.(`Awarded ${amount} credit(s) to ${list.length} user(s).`);
      await reload();
      setSelectedIds([]);
    } catch (e) {
      showToast?.(`Award failed: ${e.message}`);
    }
  }

  async function addGuest(displayName) {
    try {
      await showforgeApi.addGuestUser(displayName);
      showToast?.(`Guest "${displayName}" added.`);
      await reload();
    } catch (e) {
      showToast?.(`Add guest failed: ${e.message}`);
    }
  }

  return {
    users, loading, filteredUsers, pagedUsers, totalPages,
    stats, filterOptions, activeFilterCount, allVisibleSelected,
    search, setSearch, kindFilter, setKindFilter, statusFilter, setStatusFilter,
    selectedIds, sortKey, sortDirection, changeSort,
    page: safePage, setPage, pageSize, setPageSize,
    clearFilters, clearSelection, toggleRow, toggleAllVisible,
    awardCredits, addGuest, reload,
  };
}
