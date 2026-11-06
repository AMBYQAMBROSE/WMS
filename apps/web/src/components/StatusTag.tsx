import { STATUS_LABELS } from "@/constants/labels";
import { ACCENTS, type Accent } from "@/theme";

/** antd tag color names used in the label tables (STATUS_LABELS, AUDIT_ACTION_LABELS, ...) -> design tones */
const TONE: Record<string, Accent> = {
  default: "slate",
  blue: "blue",
  processing: "indigo",
  orange: "amber",
  gold: "amber",
  green: "green",
  purple: "violet",
  red: "red",
  cyan: "cyan",
};

export const toneOf = (color: string | undefined): Accent => TONE[color ?? "default"] ?? "slate";

/** Statuses where work is actively happening get a pulsing dot */
const LIVE = new Set(["IN_PROGRESS", "COUNTING", "PARTIALLY_RECEIVED", "PARTIALLY_SHIPPED"]);

/** Document status: dot + label in the status tone. The label carries the meaning; color only reinforces it. */
export default function StatusTag({ status }: { status: string }) {
  const label = STATUS_LABELS[status] ?? { text: status, color: "default" };
  const tone = ACCENTS[toneOf(label.color)];
  return (
    <span
      className={`wms-status${LIVE.has(status) ? " wms-status-pulse" : ""}`}
      style={{ color: tone.fg, background: tone.bg }}
      data-status={status}
    >
      <span className="wms-status-dot" aria-hidden />
      {label.text}
    </span>
  );
}
