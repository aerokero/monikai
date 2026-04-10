import { useEffect, useRef, useState } from 'react';

const getRectSize = (node) => {
  if (!node) {
    return { width: 0, height: 0 };
  }
  const rect = node.getBoundingClientRect();
  return {
    width: Math.max(0, Math.floor(rect.width)),
    height: Math.max(0, Math.floor(rect.height)),
  };
};

const useElementSize = () => {
  const ref = useRef(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;

    const update = () => {
      setSize((prev) => {
        const next = getRectSize(node);
        if (prev.width === next.width && prev.height === next.height) {
          return prev;
        }
        return next;
      });
    };

    update();

    const observer = new ResizeObserver(() => {
      update();
    });
    observer.observe(node);

    window.addEventListener('resize', update);

    return () => {
      observer.disconnect();
      window.removeEventListener('resize', update);
    };
  }, []);

  return [ref, size];
};

export default useElementSize;
