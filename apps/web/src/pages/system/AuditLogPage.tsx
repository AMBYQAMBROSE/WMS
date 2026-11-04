import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { Button, DatePicker, Input, Select, Space, Table, Tag, Typography } from "antd";
import type { Dayjs } from "dayjs";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { AuditLog } from "@/api/types";
import { ActionTag, Actor, AuditChanges, entityTitle, formatAuditTime } from "@/components/AuditTrail";
import { Toolbar } from "@/components/ui";
import { AUDIT_ACTION_LABELS, AUDIT_ENTITY_LABELS, DOC_PATHS } from "@/constants/labels";

const PAGE_SIZE = 50;

interface Filters {
  keyword?: string;
  entity_type?: string;
  action?: string;
  user_id?: string;
  range?: [Dayjs | null, Dayjs | null] | null;
  entity_id?: string;
}

/** Documents link to their detail page; the label is "<doc type> <doc no>" */
function RecordLink({ log }: { log: AuditLog }) {
  const title = entityTitle(log);
  const docType = log.entity_type === "document" ? log.entity_label?.split(" ")[0] : undefined;
  const path = docType ? DOC_PATHS[docType] : undefined;
  return path && log.action !== "DELETE" ? <Link to={`/${path}/${log.entity_id}`}>{title}</Link> : <>{title}</>;
}

export default function AuditLogPage() {
  const can = useCan();
  const [filters, setFilters] = useState<Filters>({});
  const [page, setPage] = useState(0);
  const update = (patch: Partial<Filters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setPage(0);
  };

  const { data: users } = useQuery({
    queryKey: ["users", "audit-filter"],
    queryFn: async () => (await apiClient.get<{ id: string; username: string; display_name: string }[]>("/users", { params: { limit: 500 } })).data,
    enabled: can("user.read"),
  });

  const { data, isFetching } = useQuery({
    queryKey: ["audit-logs", filters, page],
    queryFn: async () =>
      (
        await apiClient.get<AuditLog[]>("/audit-logs", {
          params: {
            keyword: filters.keyword || undefined,
            entity_type: filters.entity_type,
            action: filters.action,
            user_id: filters.user_id,
            entity_id: filters.entity_id,
            occurred_from: filters.range?.[0]?.startOf("day").toISOString(),
            occurred_to: filters.range?.[1]?.endOf("day").toISOString(),
            skip: page * PAGE_SIZE,
            limit: PAGE_SIZE + 1, // one extra row tells whether there is an older page
          },
        })
      ).data,
    placeholderData: (previous) => previous,
  });
  const rows = data?.slice(0, PAGE_SIZE) ?? [];
  const hasOlder = (data?.length ?? 0) > PAGE_SIZE;

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Toolbar
        left={
          <Space wrap>
            <Input.Search
              allowClear
              placeholder="Code or document number"
              style={{ width: 220 }}
              onSearch={(keyword) => update({ keyword })}
            />
            <Select
              allowClear
              placeholder="Record type"
              style={{ width: 190 }}
              value={filters.entity_type}
              onChange={(entity_type) => update({ entity_type })}
              options={Object.entries(AUDIT_ENTITY_LABELS).map(([value, label]) => ({ value, label }))}
            />
            <Select
              allowClear
              placeholder="Action"
              style={{ width: 130 }}
              value={filters.action}
              onChange={(action) => update({ action })}
              options={Object.entries(AUDIT_ACTION_LABELS).map(([value, { text }]) => ({ value, label: text }))}
            />
            {users && (
              <Select
                allowClear
                showSearch={{ optionFilterProp: "label" }}
                placeholder="User"
                style={{ width: 170 }}
                value={filters.user_id}
                onChange={(user_id) => update({ user_id })}
                options={users.map((u) => ({ value: u.id, label: `${u.username} (${u.display_name})` }))}
              />
            )}
            <DatePicker.RangePicker value={filters.range} onChange={(range) => update({ range })} />
            {filters.entity_id && (
              <Tag closable color="processing" onClose={() => update({ entity_id: undefined })}>
                One record only
              </Tag>
            )}
          </Space>
        }
      />
      <Table<AuditLog>
        rowKey="id"
        size="middle"
        loading={isFetching}
        dataSource={rows}
        pagination={false}
        expandable={{
          expandedRowRender: (log) => <AuditChanges changes={log.changes} action={log.action} />,
          rowExpandable: (log) => log.changes.length > 0,
        }}
        columns={[
          { title: "Time", dataIndex: "occurred_at", width: 180, render: (v: string) => formatAuditTime(v) },
          { title: "User", key: "user", width: 140, render: (_, log) => <Actor log={log} /> },
          { title: "Action", dataIndex: "action", width: 110, render: (v: string) => <ActionTag action={v} /> },
          { title: "Record", key: "record", render: (_, log) => <RecordLink log={log} /> },
          {
            title: "Changed fields",
            key: "fields",
            render: (_, log) => (
              <Typography.Text type="secondary" ellipsis style={{ maxWidth: 320 }}>
                {log.action === "UPDATE" ? log.changes.map((c) => c.field).join(", ") : ""}
              </Typography.Text>
            ),
          },
          {
            title: "",
            key: "history",
            width: 120,
            render: (_, log) => (
              <Button type="link" size="small" onClick={() => update({ entity_id: log.parent_id ?? log.entity_id })}>
                Full history
              </Button>
            ),
          },
        ]}
        footer={() => (
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <Typography.Text type="secondary">
              {rows.length ? `Showing ${page * PAGE_SIZE + 1}–${page * PAGE_SIZE + rows.length}, newest first` : ""}
            </Typography.Text>
            <Space>
              <Button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                Newer
              </Button>
              <Button disabled={!hasOlder} onClick={() => setPage((p) => p + 1)}>
                Older
              </Button>
            </Space>
          </div>
        )}
      />
    </Space>
  );
}
