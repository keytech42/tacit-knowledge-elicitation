import { ReactNode, useRef, useState } from "react";
import { createPortal } from "react-dom";

interface TooltipProps {
  text: string;
  children: ReactNode;
}

export function Tooltip({ text, children }: TooltipProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  const show = () => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    setPos({ x: rect.left + rect.width / 2, y: rect.top });
  };

  const hide = () => setPos(null);

  return (
    <span
      ref={ref}
      className="inline-flex cursor-help"
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      {children}
      {pos &&
        createPortal(
          <span
            style={{ left: pos.x, top: pos.y }}
            className="fixed -translate-x-1/2 -translate-y-full pointer-events-none px-2 py-1 -mt-1.5 text-[10px] text-white bg-gray-900 rounded shadow-lg w-max max-w-[240px] text-center leading-normal z-[9999] animate-in fade-in duration-100"
          >
            {text}
          </span>,
          document.body
        )}
    </span>
  );
}
