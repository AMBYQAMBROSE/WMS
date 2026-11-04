import { STATUS_LABELS } from "@/constants/labels";
import { ACCENTS, type Accent } from "@/theme";

/** antd tag color names used in STATUS_LABELS -> design accents */
const TONE: Record<string, Accent> = {
  default: "slate",
  blue: "blue",
  processing: "indigo",
  orange: "amber",
  green: "green",
  purple: "violet",
  red: "red",
};

/** Statuses where work is actively happening get a pulsing dot */
const LIVE = new Set(["IN_PROGRESS", "COUNTING", "PARTIALLY_RECEIVED", "PARTIALLY_SHIPPED"]);

export default function StatusTag({ status }: { status: string }) {
  const label = STATUS_LABELS[status] ?? { text: status, color: "default" };
  const tone = ACCENTS[TONE[label.color] ?? "slate"];
  return (
    <span
      className={`wms-status${LIVE.has(status) ? " wms-status-pulse" : ""}`}
      style={{ color: tone.fg, background: tone.bg }}
    >
      <span className="wms-status-dot" />
      {label.text}
    </span>
  );
}
