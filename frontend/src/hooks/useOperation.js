import { useCallback, useState } from "react";

export function useOperation({ showToast } = {}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(async (operation, options = {}) => {
    const {
      successMessage,
      errorMessage = "Operation failed.",
      onSuccess,
      onError,
    } = options;

    setPending(true);
    setError(null);

    try {
      const result = await operation();

      if (successMessage) showToast?.(successMessage);
      onSuccess?.(result);

      return result;
    } catch (caughtError) {
      setError(caughtError);
      showToast?.(caughtError?.message || errorMessage);
      onError?.(caughtError);
      throw caughtError;
    } finally {
      setPending(false);
    }
  }, [showToast]);

  return {
    pending,
    error,
    run,
    clearError: () => setError(null),
  };
}
