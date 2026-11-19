import { useState } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, DatePicker, Popconfirm, Space, Typography, message } from "antd";
import dayjs, { type Dayjs } from "dayjs";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import { Pill } from "@/components/ui";

/** Payable state of a posted receipt, in words (never color alone) */
export function PayableStatus({ due, settledOn }: { due: string | null | undefined; settledOn: string | null | undefined }) {
  if (!due) return <span className="wms-empty-value">—</span>;
  if (settledOn) {
    const late = dayjs(settledOn).diff(dayjs(due), "day");
    return (
      <Pill tone={late > 0 ? "amber" : "green"} dot>
        Settled {settledOn}
        {late > 0 ? ` · ${late} d late` : ""}
      </Pill>
    );
  }
  const overdue = dayjs().startOf("day").diff(dayjs(due), "day");
  return overdue > 0 ? (
    <Pill tone="red" dot>
      Overdue {overdue} d
    </Pill>
  ) : (
    <Pill tone="blue" dot>
      Due {due}
    </Pill>
  );
}

/** Mark a posted receipt as settled (paid) on a date, or reopen it. Needs payable.settle */
export function SettleControls({ grnId, settledOn, postedAt }: { grnId: string; settledOn: string | null | undefined; postedAt?: string | null }) {
  const can = useCan();
  const queryClient = useQueryClient();
  const [day, setDay] = useState<Dayjs>(dayjs());
  const action = useMutation({
    mutationFn: async (kind: "settle" | "reopen") =>
      (await apiClient.post(`/payables/${grnId}/${kind}`, kind === "settle" ? { settled_on: day.format("YYYY-MM-DD") } : undefined)).data,
    onSuccess: (_, kind) => {
      message.success(kind === "settle" ? "Marked as settled" : "Reopened");
      for (const key of ["payables", "grns", "analytics"]) void queryClient.invalidateQueries({ queryKey: [key] });
    },
    onError: showError,
  });
  if (!can("payable.settle")) return null;
  const posted = postedAt ? dayjs(postedAt + "Z").startOf("day") : undefined;
  if (settledOn) {
    return (
      <Popconfirm title="Reopen this payable?" description="It counts as outstanding again." onConfirm={() => action.mutate("reopen")}>
        <Button size="small" loading={action.isPending}>
          Reopen
        </Button>
      </Popconfirm>
    );
  }
  return (
    <Popconfirm
      title="Mark as settled"
      icon={null}
      description={
        <Space orientation="vertical" size={4}>
          <Typography.Text type="secondary">Date the supplier was paid</Typography.Text>
          <DatePicker
            value={day}
            allowClear={false}
            onChange={(v) => v && setDay(v)}
            disabledDate={(d) => d.isAfter(dayjs(), "day") || (posted ? d.isBefore(posted, "day") : false)}
            aria-label="Settlement date"
          />
        </Space>
      }
      okText="Settle"
      onConfirm={() => action.mutate("settle")}
    >
      <Button size="small" type="primary" ghost loading={action.isPending} data-testid={`settle-${grnId}`}>
        Settle
      </Button>
    </Popconfirm>
  );
}
