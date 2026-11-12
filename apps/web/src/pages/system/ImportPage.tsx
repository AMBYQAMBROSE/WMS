import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Card, Radio, Space, Steps, Typography } from "antd";

import { apiClient } from "@/api/client";
import type { ImportKind } from "@/api/types";
import { ImportRunner } from "@/components/ImportRunner";

const DESCRIPTIONS: Record<string, string> = {
  items: "Matched by SKU code: existing items are updated, new ones created. The base unit of an existing item cannot change.",
  locations: "Matched by location code: existing locations are updated, new ones created. Parents may be in the same file (any order).",
  partners: "Matched by code: existing partners are updated, new ones created. Type is Customer / Supplier / Both.",
  opening_stock: "Result of the pre-go-live stock count. Importing creates one posted stock adjustment (reason: opening stock). Import items and locations first.",
  purchase_orders: "One row per order line; rows with the same order ref become one purchase order. Orders are created as drafts for you to confirm.",
  sales_orders: "One row per order line; rows with the same order ref become one sales order. Orders are created as drafts for you to confirm.",
};

/** Data import: choose type -> download template -> fill in -> validate -> import */
export default function ImportPage() {
  const { data: kinds } = useQuery({
    queryKey: ["imports"],
    queryFn: async () => (await apiClient.get<ImportKind[]>("/imports")).data,
  });
  const [kindKey, setKindKey] = useState<string>();
  const kind = kinds?.find((k) => k.key === kindKey);

  return (
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Steps
        size="small"
        current={kind ? 1 : 0}
        items={[{ title: "Choose type" }, { title: "Fill template, validate and import" }]}
      />
      <Card size="small" title="What to import">
        <Radio.Group
          value={kindKey}
          onChange={(e) => setKindKey(e.target.value)}
          optionType="button"
          buttonStyle="solid"
          options={(kinds ?? []).map((k) => ({ value: k.key, label: k.name, disabled: !k.allowed }))}
        />
        {kind && (
          <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
            {DESCRIPTIONS[kind.key]}
          </Typography.Paragraph>
        )}
      </Card>
      {/* Keyed by type so switching type starts over with no file or result */}
      {kind && <ImportRunner key={kind.key} kind={kind} />}
    </Space>
  );
}
