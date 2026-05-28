export default function LoadingOverlay({
  visible,
  label = "Loading...",
}) {
  if (!visible) return null;

  return (
    <div className="loading-overlay">
      <div className="loading-card">
        <div className="loading-spinner" />

        <span>{label}</span>
      </div>
    </div>
  );
}
