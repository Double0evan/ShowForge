import { useEffect, useState, useRef } from "react";
import { apiClient } from "../../api/apiClient";
import Panel from "../shared/Panel";
import Button from "../shared/Button";
import Badge from "../shared/Badge";

const CHANNEL_FIELDS = [
  { key: "CATALOG_SFW_CHANNEL_ID",       label: "Catalog SFW" },
  { key: "CATALOG_NSFW_CHANNEL_ID",      label: "Catalog NSFW" },
  { key: "CLAIMS_SFW_CHANNEL_ID",        label: "Claims Archive SFW" },
  { key: "CLAIMS_NSFW_CHANNEL_ID",       label: "Claims Archive NSFW" },
  { key: "CLAIM_BOT_COMMANDS_CHANNEL_ID",label: "Bot Commands (item numbers)" },
  { key: "TRADE_CATEGORY_ID",            label: "Trade Category" },
  { key: "TRADE_ANNOUNCE_CHANNEL_ID",    label: "Trade Announcements" },
  { key: "TRADE_LOG_CHANNEL_ID",         label: "Trade Log" },
];

const THREAD_FIELDS = [
  { key: "UPLOAD_THREAD_RAW_SFW",  label: "RAW SFW Thread" },
  { key: "UPLOAD_THREAD_WM_SFW",   label: "Watermarked SFW Thread" },
  { key: "UPLOAD_THREAD_RAW_NSFW", label: "RAW NSFW Thread" },
  { key: "UPLOAD_THREAD_WM_NSFW",  label: "Watermarked NSFW Thread" },
];

const VERIFICATION_FIELDS = [
  { key: "VERIFIED_ROLE_ID",   label: "Verified Role ID" },
  { key: "UNVERIFIED_ROLE_ID", label: "Unverified Role ID" },
  { key: "NEWCOMER_ROLE_ID",   label: "Newcomer Role ID" },
  { key: "VERIFY_CHANNEL_ID",  label: "Verify Channel ID" },
  { key: "HONEYPOT_CHANNEL_ID",label: "Honeypot Channel ID", danger: true },
];

function useSettingsState() {
  const [values, setValues]           = useState({});
  const [dirty, setDirty]             = useState({});
  const [saving, setSaving]           = useState(false);
  const [saved, setSaved]             = useState(false);
  const [autoPublish, setAutoPublish] = useState(false);

  useEffect(() => {
    apiClient.get("/ui/settings/env")
      .then((r) => {
        const env = r.env || {};
        setValues(env);
        setAutoPublish(String(env.WATCHER_AUTO_PUBLISH) === "1");
      })
      .catch(() => {});
  }, []);

  function update(key, val) {
    setValues((v) => ({ ...v, [key]: val }));
    setDirty((d) => ({ ...d, [key]: true }));
    setSaved(false);
  }

  async function save(showToast) {
    setSaving(true);
    try {
      const fd = new FormData();
      [...CHANNEL_FIELDS, ...THREAD_FIELDS, ...VERIFICATION_FIELDS].forEach((f) =>
        fd.append(f.key, values[f.key] || "")
      );
      fd.append("WATCHER_AUTO_PUBLISH", autoPublish ? "1" : "0");
      if (values.WATCHER_PARENT_DIR) fd.append("WATCHER_PARENT_DIR", values.WATCHER_PARENT_DIR);
      await apiClient.post("/ui/settings/save", fd);
      setDirty({});
      setSaved(true);
      showToast?.("Settings saved.");
    } catch (e) {
      showToast?.(`Save failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  }

  return { values, dirty, saving, saved, autoPublish, setAutoPublish, update, save };
}

function FieldGroup({ fields, values, dirty, update }) {
  return (
    <div className="settings-field-list">
      {fields.map((f) => (
        <div key={f.key} className="settings-field">
          <label style={{ fontSize: 12, color: f.danger ? "var(--red, #e74c3c)" : "var(--muted)", display: "block", marginBottom: 4 }}>
            {f.label}
            {dirty[f.key] && <span style={{ marginLeft: 6, color: "var(--amber)", fontSize: 11 }}>unsaved</span>}
            {f.danger && <span style={{ marginLeft: 6, fontSize: 10, opacity: 0.7 }}>⚠ sensitive</span>}
          </label>
          <input
            className="drawer-input"
            value={values[f.key] || ""}
            onChange={(e) => update(f.key, e.target.value)}
            placeholder="ID"
            style={f.danger ? { borderColor: "rgba(231,76,60,0.3)" } : {}}
          />
        </div>
      ))}
    </div>
  );
}

export default function SettingsWorkspace({ showToast, activeTab }) {
  const s = useSettingsState();
  const [templatePreview, setTemplatePreview] = useState(null);
  const [uploading, setUploading]   = useState(false);
  const [dragging, setDragging]     = useState(false);
  const templateInputRef = useRef(null);

  useEffect(() => {
    apiClient.get("/ui/settings/env")
      .then((r) => { if (r.env?.WM_TEMPLATE_SFW) setTemplatePreview("/ui/settings/template/preview?rating=sfw"); })
      .catch(() => {});
  }, []);

  async function uploadTemplate(file) {
    if (!file) return;
    setUploading(true);
    try {
      for (const rating of ["sfw", "nsfw"]) {
        const fd = new FormData();
        fd.append("rating", rating);
        fd.append("file", file);
        await apiClient.post("/ui/settings/template/upload", fd);
      }
      setTemplatePreview(URL.createObjectURL(file));
      showToast?.("Watermark template updated.");
    } catch (e) {
      showToast?.(`Upload failed: ${e.message}`);
    } finally {
      setUploading(false);
    }
  }

  const hasDirty = Object.keys(s.dirty).length > 0;

  const SaveBar = () => (
    <div className="workspace-actions">
      {s.saved && !hasDirty && <Badge tone="success">Saved</Badge>}
      <Button variant="primary" onClick={() => s.save(showToast)} disabled={s.saving || !hasDirty}>
        {s.saving ? "Saving..." : "Save Changes"}
      </Button>
    </div>
  );

  // ── Templates tab ──────────────────────────────────────────────────────────
  if (activeTab === "Templates") {
    return (
      <div className="settings-workspace">
        <div className="workspace-header">
          <div><h1>Watermark Template</h1><p>Upload the PNG used for watermarking all cards.</p></div>
        </div>
        <div style={{ maxWidth: 500 }}>
          <Panel title="Watermark Template" icon="◈">
            <div
              onClick={() => templateInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); uploadTemplate(e.dataTransfer.files[0]); }}
              style={{
                border: `2px dashed ${dragging ? "var(--accent, #7c6aff)" : "rgba(255,255,255,0.1)"}`,
                borderRadius: 12, cursor: "pointer", overflow: "hidden",
                background: dragging ? "rgba(124,92,255,0.08)" : "rgba(255,255,255,0.02)",
                transition: "border-color 0.15s, background 0.15s",
                aspectRatio: "16/9", display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              {templatePreview
                ? <img src={templatePreview} alt="Template" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
                : <div style={{ textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
                    <div style={{ fontSize: 28, marginBottom: 6 }}>◈</div>
                    <div>{uploading ? "Uploading..." : "Drop template or click to upload"}</div>
                    <div style={{ fontSize: 11, marginTop: 4 }}>PNG with transparency recommended</div>
                  </div>
              }
            </div>
            <input ref={templateInputRef} type="file" accept="image/png,image/jpeg,image/webp" hidden
              onChange={(e) => uploadTemplate(e.target.files[0])} />
            {templatePreview && (
              <div style={{ marginTop: 10 }}>
                <Button onClick={() => templateInputRef.current?.click()} disabled={uploading}>
                  {uploading ? "Uploading..." : "Replace Template"}
                </Button>
              </div>
            )}
            <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 10 }}>
              Used for both SFW and NSFW watermarking. Applied to all future uploads.
            </p>
          </Panel>
        </div>
      </div>
    );
  }

  // ── Discord tab ────────────────────────────────────────────────────────────
  if (activeTab === "Discord") {
    return (
      <div className="settings-workspace">
        <div className="workspace-header">
          <div><h1>Discord Config</h1><p>Channel IDs, role IDs, and thread IDs.</p></div>
          <SaveBar />
        </div>
        <div className="settings-grid">
          <Panel title="Channels" icon="#">
            <FieldGroup fields={CHANNEL_FIELDS} values={s.values} dirty={s.dirty} update={s.update} />
          </Panel>

          <Panel title="Upload Threads" icon="⇧">
            <FieldGroup fields={THREAD_FIELDS} values={s.values} dirty={s.dirty} update={s.update} />
          </Panel>

          <Panel title="Verification & Security" icon="🔒">
            <FieldGroup fields={VERIFICATION_FIELDS} values={s.values} dirty={s.dirty} update={s.update} />
            <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 12 }}>
              The honeypot channel instantly bans any user who sends a message in it. Handle with care.
            </p>
          </Panel>
        </div>
      </div>
    );
  }

  // ── Watcher tab (default) ──────────────────────────────────────────────────
  return (
    <div className="settings-workspace">
      <div className="workspace-header">
        <div><h1>Watcher</h1><p>Upload behaviour and file paths.</p></div>
        <SaveBar />
      </div>
      <div style={{ maxWidth: 500 }}>
        <Panel title="Upload Behaviour" icon="◎">
          <div className="settings-field-list">
            <div className="settings-toggle-row">
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 3 }}>Auto-publish on upload</div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>
                  {s.autoPublish
                    ? "Cards post to catalog immediately when uploaded."
                    : "Cards are held — publish manually from Inventory."}
                </div>
              </div>
              <button type="button"
                onClick={() => { const next = !s.autoPublish; s.setAutoPublish(next); s.update("WATCHER_AUTO_PUBLISH", next ? "1" : "0"); }}
                style={{
                  flexShrink: 0, width: 48, height: 26, borderRadius: 999, border: "none",
                  cursor: "pointer", outline: "none", position: "relative", transition: "background 0.2s",
                  background: s.autoPublish ? "var(--accent, #7c6aff)" : "rgba(255,255,255,0.1)",
                }}>
                <span style={{
                  position: "absolute", top: 3, width: 20, height: 20, borderRadius: "50%",
                  background: "white", transition: "left 0.2s", boxShadow: "0 1px 4px rgba(0,0,0,0.3)",
                  left: s.autoPublish ? 25 : 3,
                }} />
              </button>
            </div>

            <div className="settings-field">
              <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 4 }}>
                Show Folder (server path)
                {s.dirty["WATCHER_PARENT_DIR"] && <span style={{ marginLeft: 6, color: "var(--amber)", fontSize: 11 }}>unsaved</span>}
              </label>
              <input className="drawer-input" value={s.values.WATCHER_PARENT_DIR || ""}
                onChange={(e) => s.update("WATCHER_PARENT_DIR", e.target.value)}
                placeholder="/home/v3bot/shows" />
            </div>
          </div>
        </Panel>

        <Panel title="Danger Zone" icon="⚠" style={{ marginTop: 16 }}>
          <strong style={{ fontSize: 13 }}>Reset Claims</strong>
          <p style={{ fontSize: 12, color: "var(--muted)", margin: "4px 0 12px" }}>
            Wipes all claims, users, and vouchers. Inventory stays intact.
          </p>
          <Button variant="danger" onClick={async () => {
            if (!window.confirm("Wipe all claims, users, and vouchers? Cannot be undone.")) return;
            try { await apiClient.post("/ui/show/reset_claims"); showToast?.("Wiped."); }
            catch (e) { showToast?.(`Failed: ${e.message}`); }
          }}>Reset Claims</Button>
        </Panel>
      </div>
    </div>
  );
}
