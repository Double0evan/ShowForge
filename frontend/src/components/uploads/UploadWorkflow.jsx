import { useRef, useState } from "react";
import { useUploadQueue } from "../../hooks/useUploadQueue";
import Button from "../shared/Button";
import Badge from "../shared/Badge";

export default function UploadWorkflow({ showToast, onUploaded }) {
  const inputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);

  const q = useUploadQueue({ showToast, onUploaded });

  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    q.addFiles(e.dataTransfer.files);
  }

  const hasReady  = q.uploadSummary.ready > 0;
  const hasStaged = q.uploadSummary.total > 0;
  const pct       = q.uploadProgress.total > 0
    ? Math.round((q.uploadProgress.done / q.uploadProgress.total) * 100)
    : 0;

  return (
    <div className="upload-workflow">

      {/* Drop zone */}
      <button
        type="button"
        className={`upload-zone single ${isDragging ? "drag-over" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <span className="upload-icon">🖼️</span>
        <strong>Drop images or click to browse</strong>
        <small>Mark SFW or NSFW after staging.</small>
        <em>PNG, JPG, JPEG, WEBP · max 12 MB each</em>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
          hidden
          onChange={(e) => { q.addFiles(e.target.files); e.target.value = ""; }}
        />
      </button>

      {/* Progress bar — always visible when uploading */}
      {q.uploading && q.uploadProgress.total > 0 && (
        <div style={{ marginTop: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--muted)", marginBottom: 4 }}>
            <span>{q.uploadProgress.done} of {q.uploadProgress.total} uploaded</span>
            <span>{pct}%</span>
          </div>
          <div style={{ height: 4, background: "rgba(255,255,255,0.08)", borderRadius: 999 }}>
            <div style={{
              height: "100%", borderRadius: 999,
              background: "var(--accent, #7c6aff)",
              width: `${pct}%`,
              transition: "width 0.3s",
            }} />
          </div>
        </div>
      )}

      {hasStaged && (
        <>
          {/* Bulk rating + queue controls */}
          <div className="upload-rating-panel">
            <div className="upload-rating-actions">
              {!q.uploading && (
                <>
                  <Button onClick={() => q.setQueueRating("sfw")}>Mark All SFW</Button>
                  <Button variant="danger" onClick={() => q.setQueueRating("nsfw")}>Mark All NSFW</Button>
                </>
              )}
            </div>
            <div className="upload-queue-actions">
              {q.uploading ? (
                <Button variant="danger" onClick={q.cancelUpload}>Cancel Upload</Button>
              ) : (
                <>
                  <Button onClick={q.clearQueue}>Clear All</Button>
                  <Button
                    variant="primary"
                    disabled={!hasReady}
                    onClick={q.queueImport}
                  >
                    Upload to Inbox
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* Queue header */}
          <div className="upload-queue">
            <div className="upload-queue-header">
              <div>
                <strong>Staged Files</strong>
                <span>
                  {q.uploadSummary.total} total
                  {q.uploadSummary.ready > 0      && ` · ${q.uploadSummary.ready} ready`}
                  {q.uploadSummary.needsRating > 0 && ` · ${q.uploadSummary.needsRating} need rating`}
                  {q.uploadSummary.uploading > 0   && ` · ${q.uploadSummary.uploading} uploading`}
                  {q.uploadSummary.done > 0        && ` · ${q.uploadSummary.done} done`}
                  {q.uploadSummary.blocked > 0     && ` · ${q.uploadSummary.blocked} blocked`}
                </span>
              </div>
            </div>

            {/* Always-visible file list */}
            <div className="upload-queue-list">
              {q.queuedFiles.map((file) => {
                const isUploading = file.status === "Uploading";
                const isDone      = file.status === "Done";
                const isBlocked   = file.status === "Blocked";
                const isLocked    = isUploading || isDone;

                return (
                  <div
                    key={file.id}
                    className={`upload-queue-item ${file.status.toLowerCase().replace(/\s+/g, "-")}`}
                    style={{ opacity: isDone ? 0.5 : 1 }}
                  >
                    <div className="upload-preview">
                      <img src={file.previewUrl} alt="" />
                    </div>

                    <div className="upload-file-main">
                      <strong>{file.filename}</strong>
                      <span>{file.sizeLabel}</span>
                      {file.error && <em style={{ color: "var(--red)" }}>{file.error}</em>}
                    </div>

                    <Badge tone={
                      isDone          ? "success"
                      : isUploading   ? "accent"
                      : file.status === "Ready"   ? "success"
                      : isBlocked     ? "danger"
                      : "default"
                    }>
                      {file.status}
                    </Badge>

                    {/* Rating selector — hidden when locked */}
                    {!isLocked && (
                      file.rating ? (
                        <span
                          className={`upload-rating-pill small ${file.rating}`}
                          style={{ cursor: "pointer" }}
                          onClick={() => q.setFileRating(file.id, file.rating === "sfw" ? "nsfw" : "sfw")}
                          title="Click to toggle rating"
                        >
                          {file.rating.toUpperCase()}
                        </span>
                      ) : (
                        <div className="upload-inline-rating">
                          <button type="button" onClick={() => q.setFileRating(file.id, "sfw")}>SFW</button>
                          <button type="button" onClick={() => q.setFileRating(file.id, "nsfw")}>NSFW</button>
                        </div>
                      )
                    )}

                    {/* Remove button — hidden when uploading or done */}
                    {!isLocked && (
                      <button
                        type="button"
                        className="upload-remove"
                        onClick={() => q.removeFile(file.id)}
                        aria-label={`Remove ${file.filename}`}
                      >
                        ×
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
