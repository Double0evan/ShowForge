import { useRef, useState } from "react";

import AppShell from "./components/layout/AppShell";
import Toast from "./components/shared/Toast";
import LoadingOverlay from "./components/shared/LoadingOverlay";

export default function App() {
  const [toast, setToast]     = useState("");
  const [loading, setLoading] = useState(false);
  const toastTimer = useRef(null);

  function showToast(message) {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 2600);
  }

  return (
    <>
      <AppShell showToast={showToast} setLoading={setLoading} />
      <Toast message={toast} onClose={() => setToast("")} />
      <LoadingOverlay visible={loading} label="Working..." />
    </>
  );
}
