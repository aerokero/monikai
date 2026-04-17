import { useCallback, useEffect, useRef, useState } from 'react';

const makeToastId = () =>
  (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;

export const useToasts = () => {
  const [toasts, setToasts] = useState([]);
  const toastTimeoutsRef = useRef(new Map());

  useEffect(() => {
    return () => {
      toastTimeoutsRef.current.forEach((timeoutId) => {
        clearTimeout(timeoutId);
      });
      toastTimeoutsRef.current.clear();
    };
  }, []);

  const pushToast = useCallback((text, variant = 'system', ttl = 3500) => {
    const id = makeToastId();
    const toast = { id, text: String(text ?? ''), variant };

    setToasts((prev) => [...prev, toast]);

    const timeoutId = window.setTimeout(() => {
      toastTimeoutsRef.current.delete(id);
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, ttl);

    toastTimeoutsRef.current.set(id, timeoutId);
  }, []);

  const dismissToast = useCallback((id) => {
    const timeoutId = toastTimeoutsRef.current.get(id);
    if (timeoutId) {
      clearTimeout(timeoutId);
      toastTimeoutsRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return {
    toasts,
    pushToast,
    dismissToast,
  };
};
