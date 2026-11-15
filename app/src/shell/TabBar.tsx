import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ComponentType,
  type KeyboardEvent,
  type PointerEvent,
} from 'react';
import './tabbar.css';

export interface TabItem<T extends string> {
  id: T;
  label: string;
  Icon: ComponentType;
}

interface Props<T extends string> {
  items: readonly TabItem<T>[];
  active: T;
  onChange: (id: T) => void;
  /** Nombre accesible de la barra. */
  label: string;
}

/** Un toque rápido no llega a mostrar el estado presionado; dejar el dedo, sí. */
const HOLD_MS = 160;
/** Lo que el dedo puede moverse antes de que el toque se vuelva arrastre. */
const DRAG_SLOP = 6;
/**
 * Rigidez de los resortes del indicador. El borde que va adelante es más
 * rígido que el de atrás: el indicador se estira al viajar y se recoge al
 * llegar, como una gota. Amortiguamiento crítico: sin rebote.
 */
const K_LEAD = 900;
const K_TRAIL = 380;

interface Edge {
  x: number;
  v: number;
}

function step(e: Edge, target: number, k: number, dt: number) {
  const c = 2 * Math.sqrt(k);
  e.v += (k * (target - e.x) - c * e.v) * dt;
  e.x += e.v * dt;
}

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function TabBar<T extends string>({ items, active, onChange, label }: Props<T>) {
  const trackRef = useRef<HTMLDivElement>(null);
  const indRef = useRef<HTMLSpanElement>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Física del indicador: fuera de React para no re-renderizar en cada cuadro.
  const left = useRef<Edge>({ x: 0, v: 0 });
  const right = useRef<Edge>({ x: 0, v: 0 });
  const target = useRef({ l: 0, r: 0, dir: 0 });
  const raf = useRef(0);
  const lastT = useRef(0);

  const drag = useRef<{ id: number; x0: number; index: number; moved: boolean } | null>(null);
  const holdTimer = useRef(0);
  const [pressed, setPressed] = useState(false);
  const [hover, setHover] = useState<number | null>(null);

  const activeIndex = Math.max(
    0,
    items.findIndex((it) => it.id === active),
  );

  const paint = useCallback(() => {
    const el = indRef.current;
    if (!el) return;
    el.style.transform = `translateX(${left.current.x}px)`;
    el.style.width = `${Math.max(0, right.current.x - left.current.x)}px`;
  }, []);

  const frame = useCallback(
    (t: number) => {
      const dt = Math.min((t - lastT.current) / 1000, 1 / 30);
      lastT.current = t;
      const { l, r, dir } = target.current;
      // Pasos de 4 ms: estable aunque el navegador se salte cuadros.
      const n = Math.max(1, Math.ceil(dt / 0.004));
      for (let i = 0; i < n; i++) {
        step(left.current, l, dir < 0 ? K_LEAD : K_TRAIL, dt / n);
        step(right.current, r, dir > 0 ? K_LEAD : K_TRAIL, dt / n);
      }
      const settled =
        Math.abs(left.current.x - l) < 0.3 &&
        Math.abs(right.current.x - r) < 0.3 &&
        Math.abs(left.current.v) < 4 &&
        Math.abs(right.current.v) < 4;
      if (settled) {
        left.current = { x: l, v: 0 };
        right.current = { x: r, v: 0 };
        raf.current = 0;
      } else {
        raf.current = requestAnimationFrame(frame);
      }
      paint();
    },
    [paint],
  );

  /** Lleva el indicador a [l, r] con el resorte, o de golpe. */
  const aim = useCallback(
    (l: number, r: number, instant = false) => {
      const prevCenter = (target.current.l + target.current.r) / 2;
      target.current = { l, r, dir: Math.sign((l + r) / 2 - prevCenter) };
      if (instant || reducedMotion()) {
        cancelAnimationFrame(raf.current);
        raf.current = 0;
        left.current = { x: l, v: 0 };
        right.current = { x: r, v: 0 };
        paint();
        return;
      }
      if (!raf.current) {
        lastT.current = performance.now();
        raf.current = requestAnimationFrame(frame);
      }
    },
    [frame, paint],
  );

  const rectOf = (i: number) => {
    const b = tabRefs.current[i];
    return b ? { l: b.offsetLeft, r: b.offsetLeft + b.offsetWidth } : { l: 0, r: 0 };
  };

  const aimAt = useCallback(
    (i: number, instant = false) => {
      const { l, r } = rectOf(i);
      aim(l, r, instant);
    },
    [aim],
  );

  const indexAt = (clientX: number) => {
    const track = trackRef.current;
    if (!track) return activeIndex;
    const x = clientX - track.getBoundingClientRect().left;
    let best = 0;
    let bestD = Infinity;
    tabRefs.current.forEach((b, i) => {
      if (!b) return;
      const d = Math.abs(b.offsetLeft + b.offsetWidth / 2 - x);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    });
    return best;
  };

  const activeIndexRef = useRef(activeIndex);
  activeIndexRef.current = activeIndex;

  // Primer pintado y cambios de tamaño: el indicador se coloca sin animar.
  useLayoutEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    aimAt(activeIndexRef.current, true);
    const ro = new ResizeObserver(() => {
      if (!drag.current) aimAt(activeIndexRef.current, true);
    });
    ro.observe(track);
    return () => ro.disconnect();
  }, [aimAt]);

  // Cambio de sección desde fuera (teclado, enlace): desliza hasta ella.
  useEffect(() => {
    if (!drag.current) aimAt(activeIndex);
  }, [activeIndex, aimAt]);

  useEffect(
    () => () => {
      cancelAnimationFrame(raf.current);
      window.clearTimeout(holdTimer.current);
    },
    [],
  );

  const press = () => {
    if (!pressed) navigator.vibrate?.(8);
    setPressed(true);
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    try {
      // Captura: el arrastre sigue aunque el dedo salga de la barra.
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* puntero ya liberado: el toque funciona igual, sin captura */
    }
    const i = indexAt(e.clientX);
    drag.current = { id: e.pointerId, x0: e.clientX, index: i, moved: false };
    setHover(i);
    aimAt(i);
    window.clearTimeout(holdTimer.current);
    holdTimer.current = window.setTimeout(press, HOLD_MS);
  };

  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    const track = trackRef.current;
    if (!d || d.id !== e.pointerId || !track) return;
    if (!d.moved && Math.abs(e.clientX - d.x0) < DRAG_SLOP) return;
    if (!d.moved) {
      d.moved = true;
      window.clearTimeout(holdTimer.current);
      press();
    }
    // Arrastrando: el indicador sigue al dedo, centrado en él y sin salirse.
    const w = rectOf(d.index).r - rectOf(d.index).l;
    const tw = track.clientWidth;
    const pad = tabRefs.current[0]?.offsetLeft ?? 0;
    const cx = Math.min(Math.max(e.clientX - track.getBoundingClientRect().left, pad + w / 2), tw - pad - w / 2);
    aim(cx - w / 2, cx + w / 2);
    setHover(indexAt(e.clientX));
  };

  const release = (e: PointerEvent<HTMLDivElement>, commit: boolean) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    window.clearTimeout(holdTimer.current);
    drag.current = null;
    setPressed(false);
    setHover(null);
    const i = commit ? (d.moved ? indexAt(e.clientX) : d.index) : activeIndex;
    aimAt(i);
    const next = items[i];
    if (commit && next && next.id !== active) onChange(next.id);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const delta = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    const to = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : activeIndex + delta;
    if (to === activeIndex && delta === 0 && e.key !== 'Home' && e.key !== 'End') return;
    e.preventDefault();
    const i = (to + items.length) % items.length;
    const next = items[i];
    if (!next) return;
    onChange(next.id);
    tabRefs.current[i]?.focus();
  };

  return (
    <nav className="kn-tabbar" aria-label={label}>
      <div className="kn-tabbar__glass">
        <div
          ref={trackRef}
          className="kn-tabbar__track"
          role="tablist"
          aria-orientation="horizontal"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={(e) => release(e, true)}
          onPointerCancel={(e) => release(e, false)}
          onKeyDown={onKeyDown}
          onContextMenu={(e) => e.preventDefault()}
        >
          <span ref={indRef} className="kn-tabbar__indicator" data-pressed={pressed || undefined} aria-hidden="true">
            <span className="kn-tabbar__pill" />
          </span>
          {items.map(({ id, label: text, Icon }, i) => {
            const selected = id === active;
            const state = pressed ? (hover === i ? 'pressed' : undefined) : selected ? 'active' : undefined;
            return (
              <button
                key={id}
                ref={(el) => {
                  tabRefs.current[i] = el;
                }}
                type="button"
                role="tab"
                id={`tab-${id}`}
                aria-selected={selected}
                aria-controls="kn-main"
                tabIndex={selected ? 0 : -1}
                className="kn-tabbar__tab"
                data-state={state}
                // El puntero se maneja en la barra; el clic solo llega aquí desde teclado.
                onClick={(e) => {
                  if (e.detail === 0) onChange(id);
                }}
              >
                <Icon />
                <span className="kn-tabbar__label">{text}</span>
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
