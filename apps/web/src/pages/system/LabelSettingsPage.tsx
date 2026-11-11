import { useState } from "react";

import { PlusOutlined, PrinterOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Checkbox,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Row,
  Segmented,
  Select,
  Space,
  Switch,
  Table,
  message,
} from "antd";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import { openPdf } from "@/api/print";
import type { LabelFieldOption, LabelLayout, LabelProfile } from "@/api/types";
import {
  LABEL_PRESETS,
  LabelPreview,
  PURPOSE_LABELS,
  describeMedia,
  describeSize,
  useLabelProfiles,
  type Purpose,
} from "@/components/labels";
import { FormSection, Pill, Toolbar } from "@/components/ui";

type ProfileForm = Omit<LabelLayout, "purpose"> & { name: string; is_default: boolean };

const PAGES = [
  { value: "A4", label: "A4 (210 × 297 mm)", w: 210, h: 297 },
  { value: "LETTER", label: "Letter (215.9 × 279.4 mm)", w: 215.9, h: 279.4 },
];

const mm = { min: 0, max: 1000, step: 0.5, precision: 2, addonAfter: "mm", style: { width: "100%" } } as const;

/**
 * Label layouts: how item and location labels sit on the paper. Office printers use sheets of labels (A4);
 * thermal label printers use rolls, one label per page. Each purpose can have a default layout; printing without
 * choosing one uses it.
 */
export default function LabelSettingsPage() {
  const can = useCan();
  const queryClient = useQueryClient();
  const [purpose, setPurpose] = useState<Purpose>("ITEM");
  const [editing, setEditing] = useState<LabelProfile | "new" | null>(null);
  const { data: profiles, isLoading } = useLabelProfiles(purpose);
  const { data: builtIn } = useQuery({
    queryKey: ["label-profiles", "built-in"],
    queryFn: async () => (await apiClient.get<Record<Purpose, LabelLayout>>("/label-profiles/built-in")).data,
    staleTime: Infinity,
  });
  const { data: fieldOptions } = useQuery({
    queryKey: ["label-profiles", "fields"],
    queryFn: async () => (await apiClient.get<Record<Purpose, LabelFieldOption[]>>("/label-profiles/fields")).data,
    staleTime: Infinity,
  });
  const canEdit = can("system.settings");

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["label-profiles", purpose] });

  const makeDefault = useMutation({
    mutationFn: async (p: LabelProfile) => apiClient.put(`/label-profiles/${p.id}`, { ...p, is_default: true }),
    onSuccess: () => {
      message.success("Default layout changed");
      void refresh();
    },
    onError: showError,
  });
  const remove = useMutation({
    mutationFn: async (p: LabelProfile) => apiClient.delete(`/label-profiles/${p.id}`),
    onSuccess: () => {
      message.success("Layout deleted");
      void refresh();
    },
    onError: showError,
  });

  const fieldName = (code: string) => fieldOptions?.[purpose]?.find((f) => f.code === code)?.name ?? code;
  const fallback = builtIn?.[purpose];

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Toolbar
        left={
          <Segmented
            value={purpose}
            onChange={(v) => setPurpose(v as Purpose)}
            options={(Object.keys(PURPOSE_LABELS) as Purpose[]).map((value) => ({ value, label: PURPOSE_LABELS[value] }))}
          />
        }
        right={
          canEdit && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setEditing("new")} data-testid="new-label-profile">
              New layout
            </Button>
          )
        }
      />
      {profiles && !profiles.some((p) => p.is_default) && fallback && (
        <Alert
          type="info"
          showIcon
          title={`No default layout for ${PURPOSE_LABELS[purpose].toLowerCase()}: printing uses the built-in layout (${describeMedia(fallback)}, ${describeSize(fallback)}).`}
        />
      )}
      <Table<LabelProfile>
        rowKey="id"
        loading={isLoading}
        dataSource={profiles}
        pagination={false}
        scroll={{ x: "max-content" }}
        columns={[
          {
            title: "Name",
            dataIndex: "name",
            render: (v: string, p) => (
              <Space size={8}>
                <span style={{ fontWeight: 500 }}>{v}</span>
                {p.is_default && <Pill tone="green" dot>Default</Pill>}
              </Space>
            ),
          },
          { title: "Paper", render: (_, p) => describeMedia(p) },
          { title: "Label size", render: (_, p) => describeSize(p) },
          { title: "Barcode", dataIndex: "barcode_type", render: (v: string) => (v === "QR" ? "QR code" : "Code 128") },
          { title: "Printed text", dataIndex: "fields", render: (v: string[]) => v.map(fieldName).join(", ") || <span className="wms-empty-value">Barcode only</span> },
          {
            title: "Actions",
            render: (_, p) => (
              <Space size={4} wrap>
                {canEdit && (
                  <Button size="small" type="text" onClick={() => setEditing(p)} aria-label={`Edit ${p.name}`}>
                    Edit
                  </Button>
                )}
                {canEdit && (
                  <Button size="small" type="text" icon={<PrinterOutlined />} onClick={() => void openPdf("/label-profiles/test-print", p)}>
                    Test print
                  </Button>
                )}
                {canEdit && !p.is_default && (
                  <Button size="small" type="text" loading={makeDefault.isPending && makeDefault.variables?.id === p.id} onClick={() => makeDefault.mutate(p)}>
                    Make default
                  </Button>
                )}
                {canEdit && (
                  <Popconfirm title={`Delete layout ${p.name}?`} onConfirm={() => remove.mutate(p)}>
                    <Button size="small" type="text" danger>
                      Delete
                    </Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />
      {editing !== null && fallback && (
        <ProfileEditor
          purpose={purpose}
          profile={editing === "new" ? null : editing}
          start={fallback}
          fields={fieldOptions?.[purpose] ?? []}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void refresh();
          }}
        />
      )}
    </Space>
  );
}

function ProfileEditor({
  purpose,
  profile,
  start,
  fields,
  onClose,
  onSaved,
}: {
  purpose: Purpose;
  profile: LabelProfile | null;
  start: LabelLayout;
  fields: LabelFieldOption[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form] = Form.useForm<ProfileForm>();
  const [testing, setTesting] = useState(false);
  const values = Form.useWatch([], form) as Partial<ProfileForm> | undefined;
  const media = Form.useWatch("media", form) ?? (profile ?? start).media;

  const initialValues: ProfileForm = profile
    ? { ...profile }
    : { ...start, name: "", is_default: false };

  const save = useMutation({
    mutationFn: async (v: ProfileForm) => {
      const body = { ...initialValues, ...v, purpose, fields: orderFields(v.fields) };
      return profile
        ? apiClient.put(`/label-profiles/${profile.id}`, { ...body, row_version: profile.row_version })
        : apiClient.post("/label-profiles", body);
    },
    onSuccess: () => {
      message.success("Layout saved");
      onSaved();
    },
    onError: showError,
  });

  // Field order on the label follows the catalog, whatever order the boxes were ticked in
  const orderFields = (picked: string[] = []) => fields.map((f) => f.code).filter((c) => picked.includes(c));

  const testPrint = async () => {
    const v = await form.validateFields().catch(() => null);
    if (!v) return;
    setTesting(true);
    await openPdf("/label-profiles/test-print", { ...initialValues, ...v, purpose, fields: orderFields(v.fields) });
    setTesting(false);
  };

  const applyPreset = (key: string) => {
    const preset = LABEL_PRESETS.find((p) => p.key === key);
    if (preset) form.setFieldsValue(preset.geometry);
  };

  const pageKey = PAGES.find((p) => p.w === values?.page_width_mm && p.h === values?.page_height_mm)?.value ?? "CUSTOM";

  return (
    <Modal
      open
      width={980}
      title={profile ? `Edit layout: ${profile.name}` : `New layout for ${PURPOSE_LABELS[purpose].toLowerCase()}`}
      onCancel={onClose}
      destroyOnHidden
      footer={[
        <Button key="test" icon={<PrinterOutlined />} loading={testing} onClick={() => void testPrint()} data-testid="label-test-print">
          Test print
        </Button>,
        <Button key="cancel" onClick={onClose}>
          Cancel
        </Button>,
        <Button key="save" type="primary" loading={save.isPending} onClick={() => form.submit()} data-testid="label-save">
          Save
        </Button>,
      ]}
    >
      <Row gutter={24}>
        <Col xs={24} md={14}>
          <Form form={form} layout="vertical" preserve={false} initialValues={initialValues} onFinish={(v) => save.mutate(v)}>
            <Row gutter={12}>
              <Col span={16}>
                <Form.Item name="name" label="Name" rules={[{ required: true, whitespace: true }]}>
                  <Input maxLength={100} placeholder="e.g. Office A4 sheets, Zebra 50 × 30" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="is_default" label="Default" valuePropName="checked">
                  <Switch />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item label="Start from label stock" extra="Fills in the sizes below; adjust them to match your labels.">
              {/* Always shows the placeholder: once applied, the sizes below are what count, and may since have changed */}
              <Select value={null} placeholder="Choose common label stock" aria-label="Start from label stock" data-testid="label-preset" options={LABEL_PRESETS.map((p) => ({ value: p.key, label: p.label }))} onChange={applyPreset} />
            </Form.Item>

            <FormSection title="Paper">
              <Form.Item name="media">
                <Radio.Group
                  optionType="button"
                  options={[
                    { value: "SHEET", label: "Sheet of labels (office printer)" },
                    { value: "ROLL", label: "Roll (label printer)" },
                  ]}
                />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name="label_width_mm" label="Label width" rules={[{ required: true }]}>
                    <InputNumber {...mm} min={5} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="label_height_mm" label="Label height" rules={[{ required: true }]}>
                    <InputNumber {...mm} min={5} />
                  </Form.Item>
                </Col>
              </Row>
              {media === "SHEET" && (
                <>
                  <Form.Item label="Page size">
                    <Select
                      value={pageKey}
                      onChange={(key) => {
                        const page = PAGES.find((p) => p.value === key);
                        if (page) form.setFieldsValue({ page_width_mm: page.w, page_height_mm: page.h });
                      }}
                      options={[...PAGES, { value: "CUSTOM", label: "Custom size" }]}
                    />
                  </Form.Item>
                  {pageKey === "CUSTOM" && (
                    <Row gutter={12}>
                      <Col span={12}>
                        <Form.Item name="page_width_mm" label="Page width" rules={[{ required: true }]}>
                          <InputNumber {...mm} min={10} />
                        </Form.Item>
                      </Col>
                      <Col span={12}>
                        <Form.Item name="page_height_mm" label="Page height" rules={[{ required: true }]}>
                          <InputNumber {...mm} min={10} />
                        </Form.Item>
                      </Col>
                    </Row>
                  )}
                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item name="columns" label="Labels across" rules={[{ required: true }]}>
                        <InputNumber min={1} max={20} precision={0} style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="rows" label="Labels down" rules={[{ required: true }]}>
                        <InputNumber min={1} max={50} precision={0} style={{ width: "100%" }} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="margin_top_mm" label="Top margin" rules={[{ required: true }]}>
                        <InputNumber {...mm} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="margin_left_mm" label="Left margin" rules={[{ required: true }]}>
                        <InputNumber {...mm} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="gap_x_mm" label="Gap between columns" rules={[{ required: true }]}>
                        <InputNumber {...mm} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="gap_y_mm" label="Gap between rows" rules={[{ required: true }]}>
                        <InputNumber {...mm} />
                      </Form.Item>
                    </Col>
                  </Row>
                </>
              )}
            </FormSection>

            <FormSection title="Content">
              <Form.Item name="barcode_type" label="Barcode">
                <Radio.Group
                  options={[
                    { value: "CODE128", label: "Code 128 (bars; any handheld scanner)" },
                    { value: "QR", label: "QR code (square; needs a 2D scanner, fits small labels)" },
                  ]}
                />
              </Form.Item>
              <Form.Item name="fields" label="Text printed with the barcode">
                <Checkbox.Group options={fields.map((f) => ({ value: f.code, label: f.name }))} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name="font_size" label="Text size" rules={[{ required: true }]}>
                    <InputNumber min={5} max={72} precision={0} addonAfter="pt" style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="padding_mm" label="Blank edge inside each label" rules={[{ required: true }]}>
                    <InputNumber {...mm} max={50} />
                  </Form.Item>
                </Col>
              </Row>
            </FormSection>
          </Form>
        </Col>
        <Col xs={24} md={10}>
          <div style={{ position: "sticky", top: 0 }}>
            <LabelPreview layout={{ ...initialValues, ...values }} />
            <Alert
              style={{ marginTop: 12 }}
              type="info"
              showIcon
              title="Check on paper before saving"
              description="Test print outlines every label. Print it at “Actual size” (not “Fit to page”) on plain paper, hold it against a label sheet, and adjust margins and gaps until the outlines match."
            />
          </div>
        </Col>
      </Row>
    </Modal>
  );
}
