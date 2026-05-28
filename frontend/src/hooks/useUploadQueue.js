import { useMemo, useRef, useState } from "react";

const ACCEPTED_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);
const MAX_FILE_SIZE_BYTES = 12 * 1024 * 1024;

function formatFileSize(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function createQueuedFile(file) {
  const validType = ACCEPTED_TYPES.has(file.type);
  const validSize = file.size <= MAX_FILE_SIZE_BYTES;
  const isValid   = validType && validSize;
  return {
    id:         `${file.name}-${file.size}-${file.lastModified}`,
    file,
    filename:   file.name,
    size:       file.size,
    sizeLabel:  formatFileSize(file.size),
    type:       file.type || "unknown",
    rating:     "",
    previewUrl: URL.createObjectURL(file),
    status:     isValid ? "Needs Rating" : "Blocked",
    error:      !validType
      ? "Only PNG, JPG, JPEG, WEBP supported."
      : !validSize ? "Exceeds 12 MB limit." : "",
  };
}

export function useUploadQueue({ showToast, onUploaded } = {}) {
  const [queuedFiles, setQueuedFiles] = useState([]);
  const [uploading, setUploading]     = useState(false);
  const [uploadProgress, setUploadProgress] = useState({ done: 0, total: 0 });
  const cancelRef = useRef(false);

  const uploadSummary = useMemo(() => ({
    total:       queuedFiles.length,
    ready:       queuedFiles.filter((f) => f.status === "Ready").length,
    needsRating: queuedFiles.filter((f) => f.status === "Needs Rating").length,
    blocked:     queuedFiles.filter((f) => f.status === "Blocked").length,
    uploading:   queuedFiles.filter((f) => f.status === "Uploading").length,
    done:        queuedFiles.filter((f) => f.status === "Done").length,
  }), [queuedFiles]);

  function addFiles(fileList) {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    const next = files.map(createQueuedFile);
    setQueuedFiles((prev) => {
      const existing = new Set(prev.map((f) => f.id));
      return [...prev, ...next.filter((f) => !existing.has(f.id))];
    });
    const blocked = next.filter((f) => f.status === "Blocked").length;
    const staged  = next.length - blocked;
    if (staged > 0)  showToast?.(`${staged} file(s) staged — select rating.`);
    if (blocked > 0) showToast?.(`${blocked} file(s) blocked by validation.`);
  }

  function setQueueRating(rating) {
    setQueuedFiles((prev) =>
      prev.map((f) =>
        f.status === "Blocked" || f.status === "Uploading" || f.status === "Done"
          ? f : { ...f, rating, status: "Ready", error: "" }
      )
    );
    showToast?.(`Queue marked ${rating.toUpperCase()}.`);
  }

  function setFileRating(id, rating) {
    setQueuedFiles((prev) =>
      prev.map((f) =>
        f.id !== id || f.status === "Blocked" || f.status === "Uploading" || f.status === "Done"
          ? f : { ...f, rating, status: "Ready", error: "" }
      )
    );
  }

  function removeFile(id) {
    setQueuedFiles((prev) => {
      const target = prev.find((f) => f.id === id);
      if (target?.previewUrl) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((f) => f.id !== id);
    });
  }

  function clearQueue() {
    queuedFiles.forEach((f) => { if (f.previewUrl) URL.revokeObjectURL(f.previewUrl); });
    setQueuedFiles([]);
    cancelRef.current = false;
  }

  function cancelUpload() {
    cancelRef.current = true;
    // Reset uploading files back to Ready so they can be retried
    setQueuedFiles((prev) =>
      prev.map((f) => f.status === "Uploading" ? { ...f, status: "Ready" } : f)
    );
    setUploading(false);
    setUploadProgress({ done: 0, total: 0 });
    showToast?.("Upload cancelled.");
  }

  async function queueImport() {
    const ready = queuedFiles.filter((f) => f.status === "Ready" && f.rating);
    if (!ready.length) {
      showToast?.("No files are ready — select SFW or NSFW first.");
      return;
    }

    cancelRef.current = false;
    setUploading(true);
    setUploadProgress({ done: 0, total: ready.length });

    let succeeded = 0;
    let failed    = 0;

    for (const f of ready) {
      // Check cancellation before each file
      if (cancelRef.current) break;

      // Mark this file as uploading
      setQueuedFiles((prev) =>
        prev.map((q) => q.id === f.id ? { ...q, status: "Uploading" } : q)
      );

      try {
        const fd = new FormData();
        fd.append("rating", f.rating);
        fd.append("files", f.file, f.filename);

        const res = await fetch("/ui/inbox/upload", { method: "POST", body: fd });
        const data = await res.json();

        if (cancelRef.current) {
          // Cancelled mid-request — reset this file
          setQueuedFiles((prev) =>
            prev.map((q) => q.id === f.id ? { ...q, status: "Ready" } : q)
          );
          break;
        }

        const ok = data.ok && (data.saved?.length > 0);
        setQueuedFiles((prev) =>
          prev.map((q) =>
            q.id === f.id
              ? { ...q, status: ok ? "Done" : "Blocked", error: ok ? "" : (data.errors?.[0] || "Upload failed") }
              : q
          )
        );
        if (ok) succeeded++; else failed++;

      } catch (e) {
        if (!cancelRef.current) {
          setQueuedFiles((prev) =>
            prev.map((q) => q.id === f.id ? { ...q, status: "Blocked", error: e.message } : q)
          );
          failed++;
        } else {
          setQueuedFiles((prev) =>
            prev.map((q) => q.id === f.id ? { ...q, status: "Ready" } : q)
          );
        }
      }

      setUploadProgress((p) => ({ ...p, done: p.done + 1 }));
    }

    if (!cancelRef.current) {
      if (succeeded > 0) {
        showToast?.(`${succeeded} file(s) uploaded to inbox.`);
        onUploaded?.();
      }
      if (failed > 0) showToast?.(`${failed} file(s) failed.`);
    }

    setUploading(false);
    setUploadProgress({ done: 0, total: 0 });
    cancelRef.current = false;
  }

  return {
    queuedFiles,
    uploadSummary,
    uploading,
    uploadProgress,
    addFiles,
    setQueueRating,
    setFileRating,
    removeFile,
    clearQueue,
    cancelUpload,
    queueImport,
  };
}
