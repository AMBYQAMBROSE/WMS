import { Tag } from "antd";

import { STATUS_LABELS } from "@/constants/labels";

export default function StatusTag({ status }: { status: string }) {
  const label = STATUS_LABELS[status] ?? { text: status, color: "default" };
  return <Tag color={label.color}>{label.text}</Tag>;
}
