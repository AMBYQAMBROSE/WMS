import { useEffect, useRef, useState } from "react";

import { flushSync } from "react-dom";

import { useUiStore } from "@/stores/uiStore";

/** Decorative motion is on: the user has not switched it off and the OS does not ask for reduced motion */
export function motionEnabled(): boolean {
  if (!useUiStore.getState().animations) return false;
  return !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** True while a view transition is drawing the theme change (main.tsx then skips its plain cross-fade) */
export let themeRevealRunning = false;

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => { ready: Promise<void>; finished: Promise<void> };
};

/**
 * Apply a color mode change with a circular reveal that grows from the click point (or the top-right corner).
 * Falls back to applying it directly where View Transitions are unsupported or motion is off.
 */
export function withThemeReveal(update: () => void, origin?: { clientX: number; clientY: number } | null) {
  const doc = document as ViewTransitionDocument;
  if (!doc.startViewTransition || !motionEnabled()) {
    update();
    return;
  }
  const x = origin?.clientX ?? window.innerWidth - 40;
  const y = origin?.clientY ?? 28;
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));

  themeRevealRunning = true;
  const transition = doc.startViewTransition(() => {
    // Render the new theme synchronously so the "after" snapshot already has it
    flushSync(update);
  });
  transition.ready
    .then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: 550, easing: "cubic-bezier(0.16, 1, 0.3, 1)", pseudoElement: "::view-transition-new(root)" }
      );
    })
    .catch(() => undefined);
  transition.finished.finally(() => {
    themeRevealRunning = false;
  });
}

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

/**
 * Animate a number from its previous value (0 on first show) to `target`. Returns the value to display.
 * Non-finite targets and disabled motion return `target` unchanged.
 */
export function useCountUp(target: number, duration = 700): number {
  const enabled = useUiStore((s) => s.animations);
  const [shown, setShown] = useState(() => (Number.isFinite(target) && motionEnabled() ? 0 : target));
  const from = useRef(shown);

  useEffect(() => {
    if (!Number.isFinite(target) || !motionEnabled()) {
      from.current = target;
      setShown(target);
      return;
    }
    const start = performance.now();
    const begin = from.current;
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const value = begin + (target - begin) * easeOutCubic(t);
      from.current = value;
      setShown(t < 1 ? value : target);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, duration, enabled]);

  return shown;
}
