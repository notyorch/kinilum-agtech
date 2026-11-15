// Íconos de la barra inferior: rellenos, en una caja de 24 px, color por currentColor.
import type { ReactNode } from 'react';

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

/** Estrella de cuatro puntas con lados cóncavos. */
function star(cx: number, cy: number, r: number): string {
  const k = r * 0.2;
  return (
    `M${cx} ${cy - r}Q${cx + k} ${cy - k} ${cx + r} ${cy}` +
    `Q${cx + k} ${cy + k} ${cx} ${cy + r}Q${cx - k} ${cy + k} ${cx - r} ${cy}` +
    `Q${cx - k} ${cy - k} ${cx} ${cy - r}Z`
  );
}

export function PinIcon() {
  return (
    <Svg>
      <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z" />
    </Svg>
  );
}

export function ChartIcon() {
  return (
    <Svg>
      <rect x="3.5" y="12" width="4.5" height="8.5" rx="1" />
      <rect x="9.75" y="7.5" width="4.5" height="13" rx="1" />
      <rect x="16" y="3.5" width="4.5" height="17" rx="1" />
    </Svg>
  );
}

export function SparkIcon() {
  return (
    <Svg>
      <path d={star(9.5, 14, 8)} />
      <path d={star(18, 6, 4.5)} />
    </Svg>
  );
}

export function DocIcon() {
  return (
    <Svg>
      <path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
    </Svg>
  );
}

export function GearIcon() {
  return (
    <Svg>
      <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.49.49 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.48.48 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.48.48 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.49.49 0 0 0-.12-.61l-2.01-1.58zM12 15.6a3.6 3.6 0 1 1 0-7.2 3.6 3.6 0 0 1 0 7.2z" />
    </Svg>
  );
}
