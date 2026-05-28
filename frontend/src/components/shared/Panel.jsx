import { useState } from "react";

function usePersistentCollapsed(title, defaultCollapsed) {
  const key = `panel_collapsed_${title}`;
  const [collapsed, setCollapsedState] = useState(() => {
    try {
      const stored = localStorage.getItem(key);
      if (stored !== null) return stored === "true";
    } catch { /* ignore */ }
    return defaultCollapsed;
  });

  function setCollapsed(val) {
    setCollapsedState(val);
    try { localStorage.setItem(key, String(val)); } catch { /* ignore */ }
  }

  return [collapsed, setCollapsed];
}

export default function Panel({
  title,
  icon,
  children,
  className = "",
  collapsible = true,
  defaultCollapsed = false,
  style,
}) {
  const [collapsed, setCollapsed] = usePersistentCollapsed(title || "", defaultCollapsed);

  return (
    <section className={`panel ${collapsed ? "collapsed" : ""} ${className}`} style={style}>
      {title && (
        <div className="panel-header">
          <div className="panel-title-wrap">
            {icon && <span className="panel-title-icon">{icon}</span>}
            <h2>{title}</h2>
          </div>

          {collapsible ? (
            <button
              className="panel-menu"
              type="button"
              aria-label={collapsed ? `Expand ${title}` : `Collapse ${title}`}
              onClick={() => setCollapsed(!collapsed)}
            >
              {collapsed ? "⌄" : "⌃"}
            </button>
          ) : (
            <button className="panel-menu" type="button" aria-label={`${title} options`}>
              ⋯
            </button>
          )}
        </div>
      )}

      {!collapsed && <div className="panel-body">{children}</div>}
    </section>
  );
}
