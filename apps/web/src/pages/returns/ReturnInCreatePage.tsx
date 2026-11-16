import { useEffect, useRef } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Form, Input, Row, message } from "antd";
import type { Dayjs } from "dayjs";
import { Link, useNavigate, useSearchParams } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document, SalesOrder } from "@/api/types";
import StockLinesEditor, { toLinePayload } from "@/components/StockLinesEditor";
import { CreateButtons, announcePosted, postDraft, preventEnterSubmit } from "@/components/documents";
import { CustomerSelect, ReasonSelect } from "@/components/selects";
import { DetailSkeleton, FormFooter, FormSection, useUnsavedChanges } from "@/components/ui";

interface LineValues {
  item_id?: string;
  uom_id?: string;
  qty?: number;
  disposition: "RESTOCK" | "SCRAP";
  location_id?: string;
  batch_no?: string;
  expiry_date?: Dayjs;
  ref_line_id?: string;
}

interface FormValues {
  partner_id: string;
  reason_code_id: string;
  remark?: string;
  lines: LineValues[];
}

export default function ReturnInCreatePage() {
  const [params] = useSearchParams();
  const soId = params.get("so") ?? undefined;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<FormValues>();
  const unsaved = useUnsavedChanges();

  const { data: so, isLoading } = useQuery({
    queryKey: ["sales-orders", soId],
    queryFn: async () => (await apiClient.get<SalesOrder>(`/sales-orders/${soId}`)).data,
    enabled: !!soId,
  });

  useEffect(() => {
    if (!so) return;
    // Prefill the returnable quantity from the original order (shipped - returned), in base units
    const lines = so.lines
      .filter((l) => l.shipped - l.returned > 0)
      .map((l) => ({
        item_id: l.item.id,
        uom_id: l.item.base_uom.id,
        qty: l.shipped - l.returned,
        disposition: "RESTOCK" as const,
        ref_line_id: l.id,
      }));
    form.setFieldsValue({ partner_id: so.partner?.id, lines: lines.length ? lines : [{ disposition: "RESTOCK" }] });
  }, [so, form]);

  const postNow = useRef(false);

  const save = useMutation({
    mutationFn: async (values: FormValues) => {
      const lines = values.lines.map((l) => {
        const payload = toLinePayload(l);
        return l.disposition === "SCRAP" ? { ...payload, location_id: null } : payload;
      });
      const draft = (await apiClient.post<Document>("/returns-in", { ...values, ref_document_id: soId ?? null, lines })).data;
      return postNow.current ? postDraft("returns-in", draft) : { doc: draft, posted: false };
    },
    onSuccess: ({ doc, posted }) => {
      unsaved.reset();
      if (posted) announcePosted(doc);
      else if (!postNow.current) message.success(`Created customer return ${doc.doc_no}; post it after inspection`);
      queryClient.invalidateQueries({ queryKey: ["returns-in"] });
      queryClient.invalidateQueries({ queryKey: ["sales-orders"] });
      queryClient.invalidateQueries({ queryKey: ["stock"] });
      navigate(`/returns-in/${doc.id}`);
    },
    onError: showError,
  });

  if (soId && isLoading) return <DetailSkeleton />;

  return (
    <Card title="New customer return">
      {so && (
        <Alert
          style={{ marginBottom: 16 }}
          type="info"
          showIcon
          title={
            <span>
              Linked to order <Link to={`/sales-orders/${so.id}`}>{so.doc_no}</Link>: returnable quantities (shipped - returned) are prefilled; reduce them or delete lines as needed.
            </span>
          }
        />
      )}
      <Form
        form={form}
        layout="vertical"
        initialValues={{ lines: [{ disposition: "RESTOCK" }] }}
        onKeyDown={preventEnterSubmit}
        onFinish={(v) => save.mutate(v)}
        {...unsaved.formProps}
      >
        <FormSection title="Return details">
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="partner_id" label="Customer" rules={[{ required: true }]}>
                <CustomerSelect style={{ width: "100%" }} disabled={!!so} />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="reason_code_id" label="Return reason" rules={[{ required: true }]}>
                <ReasonSelect category="RETURN" style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="remark" label="Remark">
                <Input maxLength={400} placeholder="Optional" />
              </Form.Item>
            </Col>
          </Row>
        </FormSection>
        <FormSection title="Lines" description="Restock puts goods back into a location; scrap only records them.">
          <StockLinesEditor form={form} name="lines" locationLabel="Restock location" withDisposition />
        </FormSection>
        <FormFooter note="Post after inspection: posting puts the restocked goods into stock">
          <CreateButtons label="Create return" postPerm="return_in.post" postNow={postNow} loading={save.isPending} />
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
