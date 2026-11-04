import {
  ApiOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  HistoryOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Descriptions, Row, Space, Table, Tag, Typography } from "antd";
import dayjs from "dayjs";

import { apiClient } from "@/api/client";
import { useCan } from "@/api/me";
import type { SystemStatus } from "@/api/types";
import { SectionTitle, StatCard } from "@/components/ui";

function since(v: string | null | undefined) {
  if (!v) return "never";
  const seconds = dayjs().diff(dayjs(v + "Z"), "second");
  if (seconds < 90) return `${seconds}s ago`;
  if (seconds < 90 * 60) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 36 * 3600) return `${Math.round(seconds / 3600)} h ago`;
  return dayjs(v + "Z").format("YYYY-MM-DD HH:mm");
}

/** Everything comes from the database, so it is the same whichever backend process answers. Refreshes every 15 s. */
export default function SystemHealthPage() {
  const can = useCan();
  const { data, isFetching, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["system-status"],
    queryFn: async () => (await apiClient.get<SystemStatus>("/system/status")).data,
    refetchInterval: 15_000,
  });
  if (!data) return <Card loading />;

  const migrationOk = data.db_revision === data.code_revision;
  const problems = [
    !migrationOk && "The database schema does not match this version: run the upgrade script (alembic upgrade head).",
    !data.worker.healthy && "The background worker is not running: integration events are queuing up and nothing is sent to external systems.",
    data.integration.failed > 0 && `${data.integration.failed} integration deliveries failed after all retries and need manual handling.`,
  ].filter(Boolean) as string[];

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      {problems.length ? (
        <Alert type="warning" showIcon title="Needs attention" description={<ul style={{ margin: 0, paddingLeft: 18 }}>{problems.map((p) => <li key={p}>{p}</li>)}</ul>} />
      ) : (
        <Alert type="success" showIcon title="All systems normal" />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={12} md={8} xl={6}>
          <StatCard
            label="Database"
            value={`${data.database.latency_ms} ms`}
            icon={<DatabaseOutlined />}
            accent={data.database.latency_ms < 100 ? "green" : "amber"}
            hint={data.database.size_mb != null ? `${data.database.size_mb.toLocaleString()} MB` : "Round-trip time"}
          />
        </Col>
        <Col xs={12} md={8} xl={6}>
          <StatCard
            label="Background worker"
            value={data.worker.healthy ? "Running" : "Stopped"}
            icon={<CloudServerOutlined />}
            accent={data.worker.healthy ? "green" : "red"}
            hint={`Last heartbeat ${since(data.worker.last_seen)}`}
          />
        </Col>
        <Col xs={12} md={8} xl={6}>
          <StatCard
            label="Integration queue"
            value={data.integration.pending + data.integration.running}
            icon={<ApiOutlined />}
            accent={data.integration.failed ? "red" : data.integration.pending > 100 ? "amber" : "cyan"}
            hint={data.integration.oldest_pending_at ? `Oldest waiting since ${since(data.integration.oldest_pending_at)}` : `${data.integration.failed} failed`}
            to={can("integration.read") ? "/integration" : undefined}
          />
        </Col>
        <Col xs={12} md={8} xl={6}>
          <StatCard
            label="Changes in 24 h"
            value={data.audit_entries_24h}
            icon={<HistoryOutlined />}
            accent="violet"
            hint="Audit log entries"
            to={can("audit.read") ? "/audit-log" : undefined}
          />
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card>
            <SectionTitle
              title="Version and monitoring"
              extra={
                <Button size="small" icon={<ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>
                  Refresh
                </Button>
              }
            />
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Version">{data.version}</Descriptions.Item>
              <Descriptions.Item label="Database schema">
                <Typography.Text code>{data.db_revision ?? "unknown"}</Typography.Text>{" "}
                {migrationOk ? <Tag color="green">up to date</Tag> : <Tag color="red">expected {data.code_revision}</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="Read committed snapshot">
                {data.database.read_committed_snapshot == null ? "unknown" : data.database.read_committed_snapshot ? "On" : <Tag color="orange">Off</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="OpenTelemetry">
                {data.telemetry.otel_enabled ? (
                  <Tag color="green" icon={<ThunderboltOutlined />}>Exporting traces and metrics</Tag>
                ) : (
                  <Typography.Text type="secondary">Off (set OTEL_EXPORTER_OTLP_ENDPOINT to send to a collector)</Typography.Text>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="Logs">
                {data.telemetry.log_format.toUpperCase()}, slow request threshold {data.telemetry.slow_request_ms} ms
              </Descriptions.Item>
              <Descriptions.Item label="Updated">{dayjs(dataUpdatedAt).format("HH:mm:ss")}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card>
            <SectionTitle title="Largest tables" />
            {data.tables.length ? (
              <Table
                rowKey="name"
                size="small"
                pagination={false}
                dataSource={data.tables}
                columns={[
                  { title: "Table", dataIndex: "name", render: (v: string) => <Typography.Text code>{v}</Typography.Text> },
                  { title: "Rows", dataIndex: "rows", align: "right", render: (v: number) => v.toLocaleString() },
                ]}
              />
            ) : (
              <Typography.Text type="secondary">
                Not available: the database login needs the VIEW DATABASE STATE permission to show sizes.
              </Typography.Text>
            )}
          </Card>
        </Col>
      </Row>
    </Space>
  );
}
