import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Space, Table } from "antd";

import { apiClient } from "@/api/client";
import type { PartnerLedgerRow } from "@/api/types";
import { STICKY_HEADER } from "@/components/ui";
import { exportReport, presetRange, rangeParams, ReportFilters, TruncatedHint, type Range, type ReportPage } from "@/components/reports";
import { PartnerSelect } from "@/components/selects";

/** Partner ledger (Ninso SupplierLedger / OutletLedger): received/shipped/returned quantities per partner in the period */
export default function PartnerLedgerPage() {
  const [range, setRange] = useState<Range>(presetRange(30));
  const [partnerId, setPartnerId] = useState<string>();
  const params = { ...rangeParams(range), partner_id: partnerId };
  const { data, isFetching } = useQuery({
    queryKey: ["reports", "partner-ledger", params],
    queryFn: async () => (await apiClient.get<ReportPage<PartnerLedgerRow>>("/reports/partner-ledger", { params })).data,
    placeholderData: (prev) => prev,
  });

  const exportCsv = () => exportReport("/reports/partner-ledger", params);

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <ReportFilters range={range} onRangeChange={setRange} onExport={exportCsv} exportDisabled={!data?.total}>
        <PartnerSelect allowClear placeholder="All partners" style={{ width: 240 }} value={partnerId} onChange={setPartnerId} data-testid="ledger-partner" />
      </ReportFilters>
      <TruncatedHint page={data} />
      <Table<PartnerLedgerRow>
        rowKey={(r) => `${r.partner.id}-${r.item.id}`}
        size="small"
        loading={isFetching && !data}
        className={isFetching && data ? "wms-refreshing" : undefined}
        sticky={STICKY_HEADER}
        dataSource={data?.rows}
        scroll={{ x: "max-content" }}
        columns={[
          { title: "Partner", render: (_, r) => `${r.partner.code} ${r.partner.name}` },
          { title: "SKU", render: (_, r) => <span className="wms-mono">{r.item.sku_code}</span> },
          { title: "Item", render: (_, r) => r.item.name },
          { title: "Unit", render: (_, r) => r.item.base_uom.code },
          { title: "Received", dataIndex: "received", align: "right" },
          { title: "Returned to supplier", dataIndex: "returned_to_supplier", align: "right" },
          { title: "Shipped", dataIndex: "shipped", align: "right" },
          { title: "Customer returns", dataIndex: "returned_by_customer", align: "right" },
          { title: "Documents", dataIndex: "documents", align: "right" },
        ]}
      />
    </Space>
  );
}
