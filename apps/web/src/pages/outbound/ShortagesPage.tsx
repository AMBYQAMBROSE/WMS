import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Alert, Input, Space, Table, Tag, Typography } from "antd";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import type { ShortageRow } from "@/api/types";
import { Toolbar } from "@/components/ui";

/** Ninso OrderShortage: quantity not yet allocated across orders in progress */
export default function ShortagesPage() {
  const [keyword, setKeyword] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["sales-orders", "shortages"],
    queryFn: async () => (await apiClient.get<ShortageRow[]>("/sales-orders/shortages")).data,
  });

  // The data set is small, so filter by order no./customer/SKU/item name in the browser
  const kw = keyword.trim().toLowerCase();
  const rows = kw
    ? data?.filter((r) => [r.so_doc_no, r.customer, r.item.sku_code, r.item.name].some((v) => v.toLowerCase().includes(kw)))
    : data;

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        title="Quantity not yet allocated across all orders in progress. Available warehouse-wide > 0 means re-allocating now would cover it (e.g. after replenishment or receiving); 0 means it must be purchased or transferred."
      />
      <Toolbar
        left={
          <Input.Search
            allowClear
            placeholder="Search by order no./customer/SKU/item"
            style={{ width: 340 }}
            onChange={(e) => setKeyword(e.target.value)}
          />
        }
        right={rows && <Typography.Text type="secondary">{rows.length} lines</Typography.Text>}
      />
      <Table<ShortageRow>
        rowKey="line_id"
        loading={isLoading}
        dataSource={rows}
        columns={[
          { title: "Order", render: (_, r) => <Link to={`/sales-orders/${r.so_id}`}>{r.so_doc_no}</Link> },
          { title: "Customer", dataIndex: "customer" },
          { title: "Requested ship date", dataIndex: "expected_date" },
          { title: "SKU", render: (_, r) => r.item.sku_code },
          { title: "Item", render: (_, r) => r.item.name },
          { title: "Ordered", render: (_, r) => `${r.ordered} ${r.item.base_uom.code}` },
          { title: "Unallocated", dataIndex: "unallocated" },
          {
            title: "Available warehouse-wide",
            render: (_, r) => (r.available > 0 ? <Tag color="green">{r.available} can re-allocate</Tag> : <Tag color="red">0</Tag>),
          },
        ]}
      />
    </Space>
  );
}
