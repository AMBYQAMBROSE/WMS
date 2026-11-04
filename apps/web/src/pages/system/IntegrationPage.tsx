import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import dayjs from "dayjs";
import { Link } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { Connector, ConnectorWithSecret, EventType, IntegrationJob, IntegrationJobDetail, IntegrationSummary } from "@/api/types";
import { formatDateTime, preventEnterSubmit } from "@/components/documents";
import { DOC_PATHS, DOC_TYPE_LABELS } from "@/constants/labels";

const KEY = "integration";

const JOB_STATUS: Record<string, { text: string; color: string }> = {
  PENDING: { text: "Pending", color: "blue" },
  RUNNING: { text: "Delivering", color: "processing" },
  SUCCEEDED: { text: "Succeeded", color: "green" },
  FAILED: { text: "Failed", color: "red" },
};

interface ConnectorForm {
  code: string;
  name: string;
  endpoint_url: string;
  event_types: string[];
  headers?: { name?: string; value?: string }[];
  timeout_seconds: number;
  max_attempts: number;
  is_active: boolean;
}

function WorkerStatus({ summary }: { summary?: IntegrationSummary }) {
  if (!summary) return null;
  const seen = summary.worker_last_seen ? dayjs(summary.worker_last_seen + "Z") : null;
  const stale = !seen || dayjs().diff(seen, "second") > 60;
  return (
    <Alert
      type={stale ? "warning" : "success"}
      showIcon
      data-testid="worker-status"
      title={
        stale
          ? `The delivery worker is not running${seen ? ` (last seen ${seen.format("MM-DD HH:mm")})` : ""}: events are queuing and will be delivered once it is back. Check the worker service.`
          : `Delivery worker running · pending ${summary.jobs.PENDING ?? 0} · failed ${summary.jobs.FAILED ?? 0} · succeeded ${summary.jobs.SUCCEEDED ?? 0}`
      }
    />
  );
}

function SecretModal({ connector, onClose }: { connector: ConnectorWithSecret | null; onClose: () => void }) {
  return (
    <Modal open={!!connector} title="Signing secret" onOk={onClose} onCancel={onClose} cancelButtonProps={{ style: { display: "none" } }} okText="I have saved it">
      <Alert type="warning" showIcon title="The secret is shown only this once. Copy it to the receiving side; if lost it can only be regenerated." style={{ marginBottom: 12 }} />
      <Typography.Paragraph copyable code data-testid="secret-value">
        {connector?.secret}
      </Typography.Paragraph>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        The receiver verifies the X-WMS-Signature header with it: sha256=HMAC_SHA256(secret, "timestamp.body"); see docs/integration.md.
      </Typography.Text>
    </Modal>
  );
}

function ConnectorModal({
  open,
  editing,
  eventTypes,
  onClose,
  onCreated,
}: {
  open: boolean;
  editing: Connector | null;
  eventTypes: EventType[];
  onClose: () => void;
  onCreated: (c: ConnectorWithSecret) => void;
}) {
  const [form] = Form.useForm<ConnectorForm>();
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: async (v: ConnectorForm) => {
      const body = {
        ...v,
        extra_headers: Object.fromEntries((v.headers ?? []).filter((h) => h.name).map((h) => [h.name!, h.value ?? ""])),
      };
      return editing
        ? (await apiClient.put<Connector>(`/integration/connectors/${editing.id}`, body)).data
        : (await apiClient.post<ConnectorWithSecret>("/integration/connectors", body)).data;
    },
    onSuccess: (c) => {
      queryClient.invalidateQueries({ queryKey: [KEY] });
      onClose();
      if ("secret" in c) onCreated(c as ConnectorWithSecret);
      else message.success("Saved");
    },
    onError: showError,
  });

  // Subscribable events grouped by document type
  const groups = Object.entries(
    eventTypes.reduce<Record<string, EventType[]>>((acc, e) => ({ ...acc, [e.doc_type]: [...(acc[e.doc_type] ?? []), e] }), {}),
  );

  return (
    <Modal
      open={open}
      title={editing ? `Edit connector ${editing.code}` : "New connector"}
      width={720}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={save.isPending}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        preserve={false}
        onKeyDown={preventEnterSubmit}
        onFinish={(v) => save.mutate(v)}
        initialValues={
          editing
            ? { ...editing, headers: Object.entries(editing.extra_headers).map(([name, value]) => ({ name, value })) }
            : { event_types: [], timeout_seconds: 10, max_attempts: 8, is_active: true, headers: [] }
        }
      >
        <Space size="large" wrap>
          <Form.Item name="code" label="Code" rules={[{ required: true }]}>
            <Input maxLength={30} disabled={!!editing} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="name" label="Name (receiving system)" rules={[{ required: true }]}>
            <Input maxLength={100} style={{ width: 240 }} placeholder="e.g. SAP ERP, transport management" />
          </Form.Item>
          <Form.Item name="is_active" label="Active" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Space>
        <Form.Item name="endpoint_url" label="Endpoint URL" rules={[{ required: true }, { pattern: /^https?:\/\/.+/, message: "Must start with http:// or https://" }]}>
          <Input maxLength={500} placeholder="https://erp.example.local/wms/webhook" />
        </Form.Item>
        <Form.Item name="event_types" label="Subscribed events" rules={[{ required: true, type: "array", min: 1, message: "Select at least one event" }]}>
          <Checkbox.Group style={{ width: "100%" }}>
            <Space orientation="vertical" style={{ width: "100%" }}>
              {groups.map(([docType, events]) => (
                <div key={docType}>
                  <Typography.Text type="secondary" style={{ display: "inline-block", width: 80 }}>
                    {DOC_TYPE_LABELS[docType] ?? docType}
                  </Typography.Text>
                  {events.map((e) => (
                    <Checkbox key={e.code} value={e.code}>
                      {e.name}
                    </Checkbox>
                  ))}
                </div>
              ))}
            </Space>
          </Checkbox.Group>
        </Form.Item>
        <Space size="large" wrap>
          <Form.Item name="timeout_seconds" label="Timeout (s)">
            <InputNumber min={1} max={60} />
          </Form.Item>
          <Form.Item name="max_attempts" label="Max attempts">
            <InputNumber min={1} max={20} />
          </Form.Item>
        </Space>
        <Typography.Text strong>Extra headers (if the receiver requires authentication, e.g. Authorization)</Typography.Text>
        <Form.List name="headers">
          {(fields, { add, remove }) => (
            <>
              {fields.map((f) => (
                <Space key={f.key} style={{ display: "flex", marginTop: 8 }}>
                  <Form.Item name={[f.name, "name"]} noStyle>
                    <Input placeholder="Name" style={{ width: 180 }} />
                  </Form.Item>
                  <Form.Item name={[f.name, "value"]} noStyle>
                    <Input placeholder="Value" style={{ width: 360 }} />
                  </Form.Item>
                  <Button onClick={() => remove(f.name)}>Remove</Button>
                </Space>
              ))}
              <Button type="dashed" onClick={() => add({})} style={{ marginTop: 8 }}>
                Add header
              </Button>
            </>
          )}
        </Form.List>
      </Form>
    </Modal>
  );
}

function JobDrawer({ jobId, onClose }: { jobId: string | null; onClose: () => void }) {
  const can = useCan();
  const queryClient = useQueryClient();
  const { data: job } = useQuery({
    queryKey: [KEY, "job", jobId],
    queryFn: async () => (await apiClient.get<IntegrationJobDetail>(`/integration/jobs/${jobId}`)).data,
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data && ["PENDING", "RUNNING"].includes(q.state.data.status) ? 3000 : false),
  });
  const retry = useMutation({
    mutationFn: async () => (await apiClient.post(`/integration/jobs/${jobId}/retry`)).data,
    onSuccess: () => {
      message.success("Queued again; it will be delivered shortly");
      queryClient.invalidateQueries({ queryKey: [KEY] });
    },
    onError: showError,
  });
  const pretty = (() => {
    try {
      return job?.payload ? JSON.stringify(JSON.parse(job.payload), null, 2) : "";
    } catch {
      return job?.payload ?? "";
    }
  })();

  return (
    <Drawer open={!!jobId} onClose={onClose} size={720} title="Delivery details" destroyOnHidden>
      {job && (
        <Space orientation="vertical" style={{ width: "100%" }}>
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="Status">
              <Tag color={JOB_STATUS[job.status].color}>{JOB_STATUS[job.status].text}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Connector">{job.connector_name}</Descriptions.Item>
            <Descriptions.Item label="Event">{job.event_name}</Descriptions.Item>
            <Descriptions.Item label="Document">
              {job.doc_no && job.doc_type && job.document_id ? (
                <Link to={`/${DOC_PATHS[job.doc_type]}/${job.document_id}`}>{job.doc_no}</Link>
              ) : (
                "-"
              )}
            </Descriptions.Item>
            <Descriptions.Item label="Attempts">{job.attempts}</Descriptions.Item>
            <Descriptions.Item label="Next attempt">{job.status === "PENDING" ? formatDateTime(job.next_attempt_at) : "-"}</Descriptions.Item>
          </Descriptions>
          {["FAILED", "PENDING"].includes(job.status) && can("integration.manage") && (
            <Button type="primary" onClick={() => retry.mutate()} loading={retry.isPending}>
              {job.status === "FAILED" ? "Redeliver" : "Deliver now"}
            </Button>
          )}
          <Typography.Title level={5}>Calls</Typography.Title>
          <Table
            size="small"
            rowKey="attempt_no"
            pagination={false}
            dataSource={job.logs}
            expandable={{
              rowExpandable: (l) => !!(l.response_body || l.error),
              expandedRowRender: (l) => (
                <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 12 }}>{[l.error, l.response_body].filter(Boolean).join("\n")}</pre>
              ),
            }}
            columns={[
              { title: "#", dataIndex: "attempt_no", width: 48 },
              { title: "Time", dataIndex: "requested_at", render: formatDateTime },
              { title: "Result", render: (_, l) => (l.success ? <Tag color="green">Succeeded</Tag> : <Tag color="red">Failed</Tag>) },
              { title: "Status code", dataIndex: "status_code", render: (v) => v ?? "-" },
              { title: "Duration", dataIndex: "duration_ms", render: (v: number) => `${v} ms` },
            ]}
          />
          <Typography.Title level={5}>Payload</Typography.Title>
          <pre style={{ background: "var(--ant-color-fill-quaternary)", border: "1px solid var(--wms-surface-border)", padding: 12, borderRadius: 10, fontSize: 12, maxHeight: 360, overflow: "auto" }} data-testid="job-payload">
            {pretty}
          </pre>
        </Space>
      )}
    </Drawer>
  );
}

/** Integrations: push document events to external systems (ERP, TMS, ...), view the delivery log, redeliver failures */
export default function IntegrationPage() {
  const can = useCan();
  const manage = can("integration.manage");
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Connector | null>(null);
  const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState<ConnectorWithSecret | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [filters, setFilters] = useState<{ status?: string; connector_id?: string; doc_no?: string }>({});

  const { data: summary } = useQuery({
    queryKey: [KEY, "summary"],
    queryFn: async () => (await apiClient.get<IntegrationSummary>("/integration/summary")).data,
    refetchInterval: 15_000,
  });
  const { data: eventTypes = [] } = useQuery({
    queryKey: [KEY, "event-types"],
    queryFn: async () => (await apiClient.get<EventType[]>("/integration/event-types")).data,
  });
  const eventName = Object.fromEntries(eventTypes.map((e) => [e.code, e.name]));
  const connectors = useQuery({
    queryKey: [KEY, "connectors"],
    queryFn: async () => (await apiClient.get<Connector[]>("/integration/connectors")).data,
  });
  const jobs = useQuery({
    queryKey: [KEY, "jobs", filters],
    queryFn: async () => (await apiClient.get<IntegrationJob[]>("/integration/jobs", { params: filters })).data,
    refetchInterval: 10_000,
  });

  const act = useMutation({
    mutationFn: async ({ id, action }: { id: string; action: "test" | "rotate" | "delete" }) => {
      if (action === "delete") return (await apiClient.delete(`/integration/connectors/${id}`)).data;
      if (action === "rotate") return (await apiClient.post<ConnectorWithSecret>(`/integration/connectors/${id}/rotate-secret`)).data;
      return (await apiClient.post(`/integration/connectors/${id}/test`)).data;
    },
    onSuccess: (result, { action }) => {
      queryClient.invalidateQueries({ queryKey: [KEY] });
      if (action === "rotate") setSecret(result as ConnectorWithSecret);
      else message.success(action === "test" ? "Test delivery queued; check the Delivery log in a few seconds" : "Deleted");
    },
    onError: showError,
  });

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <WorkerStatus summary={summary} />
      <Tabs
        items={[
          {
            key: "connectors",
            label: "Connectors",
            children: (
              <Space orientation="vertical" style={{ width: "100%" }}>
                {manage && (
                  <Button type="primary" onClick={() => setCreating(true)}>
                    New connector
                  </Button>
                )}
                <Table<Connector>
                  rowKey="id"
                  loading={connectors.isLoading}
                  dataSource={connectors.data}
                  pagination={false}
                  columns={[
                    { title: "Code", dataIndex: "code" },
                    { title: "Name", dataIndex: "name" },
                    { title: "Endpoint URL", dataIndex: "endpoint_url", ellipsis: true },
                    {
                      title: "Subscribed events",
                      dataIndex: "event_types",
                      render: (v: string[]) => (
                        <Typography.Text title={v.map((c) => eventName[c] ?? c).join(", ")}>{v.length}</Typography.Text>
                      ),
                    },
                    { title: "Secret", dataIndex: "secret_hint" },
                    { title: "Status", dataIndex: "is_active", render: (v: boolean) => <Badge status={v ? "success" : "default"} text={v ? "Active" : "Disabled"} /> },
                    {
                      title: "Actions",
                      render: (_, c) =>
                        manage && (
                          <Space size={4} wrap>
                            <Button size="small" onClick={() => setEditing(c)}>Edit</Button>
                            <Button size="small" onClick={() => act.mutate({ id: c.id, action: "test" })} disabled={!c.is_active}>
                              Send test
                            </Button>
                            <Popconfirm title="The old secret stops working immediately and the receiver must be updated. Continue?" onConfirm={() => act.mutate({ id: c.id, action: "rotate" })}>
                              <Button size="small">Regenerate secret</Button>
                            </Popconfirm>
                            <Popconfirm title="Nothing more will be delivered and undelivered jobs are cancelled. Continue?" onConfirm={() => act.mutate({ id: c.id, action: "delete" })}>
                              <Button size="small" danger>Delete</Button>
                            </Popconfirm>
                          </Space>
                        ),
                    },
                  ]}
                />
              </Space>
            ),
          },
          {
            key: "jobs",
            label: "Delivery log",
            children: (
              <Space orientation="vertical" style={{ width: "100%" }}>
                <Space wrap>
                  <Select
                    allowClear
                    placeholder="All statuses"
                    style={{ width: 140 }}
                    value={filters.status}
                    onChange={(status) => setFilters((f) => ({ ...f, status }))}
                    options={Object.entries(JOB_STATUS).map(([value, s]) => ({ value, label: s.text }))}
                    data-testid="job-status-filter"
                  />
                  <Select
                    allowClear
                    placeholder="All connectors"
                    style={{ width: 200 }}
                    value={filters.connector_id}
                    onChange={(connector_id) => setFilters((f) => ({ ...f, connector_id }))}
                    options={(connectors.data ?? []).map((c) => ({ value: c.id, label: c.name }))}
                  />
                  <Input.Search
                    allowClear
                    placeholder="Document no."
                    style={{ width: 200 }}
                    onSearch={(doc_no) => setFilters((f) => ({ ...f, doc_no: doc_no || undefined }))}
                  />
                </Space>
                <Table<IntegrationJob>
                  rowKey="id"
                  size="small"
                  loading={jobs.isLoading}
                  dataSource={jobs.data}
                  onRow={(job) => ({ onClick: () => setJobId(job.id), style: { cursor: "pointer" } })}
                  columns={[
                    { title: "Time", dataIndex: "created_at", render: formatDateTime },
                    { title: "Event", dataIndex: "event_name" },
                    { title: "Document no.", dataIndex: "doc_no", render: (v) => v ?? "-" },
                    { title: "Connector", dataIndex: "connector_name" },
                    { title: "Status", dataIndex: "status", render: (s: string) => <Tag color={JOB_STATUS[s].color}>{JOB_STATUS[s].text}</Tag> },
                    { title: "Attempts", dataIndex: "attempts" },
                    { title: "Last error", dataIndex: "last_error", ellipsis: true, render: (v) => v ?? "" },
                  ]}
                />
              </Space>
            ),
          },
        ]}
      />
      <ConnectorModal
        open={creating || !!editing}
        editing={editing}
        eventTypes={eventTypes}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        onCreated={setSecret}
      />
      <SecretModal connector={secret} onClose={() => setSecret(null)} />
      <JobDrawer jobId={jobId} onClose={() => setJobId(null)} />
    </Space>
  );
}
