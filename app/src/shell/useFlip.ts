import { useLayoutEffect, useRef } from 'react';

/**
 * Animación FLIP para listas que se reordenan: cada elemento se desliza de su
 * lugar anterior al nuevo (250 ms, ease-out). Solo se mueven los que cambian
 * de lugar. Sin animación si el usuario pidió reducir el movimiento.
 *
 *   const register = useFlip(order.join());
 *   <article ref={register(id)} />
 */
export function useFlip(orderKey: string) {
  const nodes = useRef(new Map<string, HTMLElement>());
  const last = useRef(new Map<string, number>());

  useLayoutEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const next = new Map<string, number>();
    nodes.current.forEach((el, id) => {
      const top = el.getBoundingClientRect().top + window.scrollY;
      next.set(id, top);
      const prev = last.current.get(id);
      if (!reduce && prev !== undefined && Math.abs(prev - top) > 1) {
        el.animate([{ transform: `translateY(${prev - top}px)` }, { transform: 'none' }], {
          duration: 250,
          easing: 'cubic-bezier(0.2, 0, 0, 1)',
        });
      }
    });
    last.current = next;
  }, [orderKey]);

  return (id: string) => (el: HTMLElement | null) => {
    if (el) nodes.current.set(id, el);
    else nodes.current.delete(id);
  };
}
