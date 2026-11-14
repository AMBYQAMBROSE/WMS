import { useRef } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Col, Form, Input, Row, message } from "antd";
import type { Dayjs } from "dayjs";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import StockLinesEditor, { toLinePayload } from "@/components/StockLinesEditor";
import { CreateButtons, announcePosted, postDraft, preventEnterSubmit } from "@/components/documents";
import { ReasonSelect, SupplierSelect } from "@/components/selects";
import { FormFooter, FormSection, useUnsavedChanges } from "@/components/ui";

interface FormValues {
  partner_id: string;
  reason_code_id: string;
  remark?: string;
  lines: { item_id?: string; uom_id?: string; qty?: number; location_id?: string; batch_no?: string; expiry_date?: Dayjs }[];
}

export default function ReturnOutCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<FormValues>();
  const unsaved = useUnsavedChanges();

  const postNow = useRef(false);

  const save = useMutation({
    mutationFn: async (values: FormValues) => {
      const draft = (await apiClient.post<Document>("/returns-out", { ...values, lines: values.lines.map(toLinePayload) })).data;
      return postNow.current ? postDraft("returns-out", draft) : { doc: draft, posted: false };
    },
    onSuccess: ({ doc, posted }) => {
      unsaved.reset();
      if (posted) announcePosted(doc);
      else if (!postNow.current) message.success(`Created return to supplier ${doc.doc_no}; post it once the goods are handed over`);
      queryClient.invalidateQueries({ queryKey: ["returns-out"] });
      queryClient.invalidateQueries({ queryKey: ["stock"] });
      navigate(`/returns-out/${doc.id}`);
    },
    onError: showError,
  });

  return (
    <Card title="New return to supplier">
      <Form form={form} layout="vertical" initialValues={{ lines: [{}] }} onKeyDown={preventEnterSubmit} onFinish={(v) => save.mutate(v)} {...unsaved.formProps}>
        <FormSection title="Return details">
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="partner_id" label="Supplier" rules={[{ required: true }]}>
                <SupplierSelect style={{ width: "100%" }} />
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
        <FormSection title="Lines" description="Choose the location the goods leave from: its item, batch and free quantity are filled in.">
          <StockLinesEditor form={form} name="lines" locationLabel="From location" stockSource />
        </FormSection>
        <FormFooter note="Post once the goods are handed over: posting takes them out of stock">
          <CreateButtons label="Create return to supplier" postPerm="return_out.post" postNow={postNow} loading={save.isPending} />
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
