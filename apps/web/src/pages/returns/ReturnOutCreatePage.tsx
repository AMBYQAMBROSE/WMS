import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, Space, message } from "antd";
import type { Dayjs } from "dayjs";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import StockLinesEditor, { toLinePayload } from "@/components/StockLinesEditor";
import { preventEnterSubmit } from "@/components/documents";
import { ReasonSelect, SupplierSelect } from "@/components/selects";
import { FormFooter } from "@/components/ui";

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

  const save = useMutation({
    mutationFn: async (values: FormValues) =>
      (await apiClient.post<Document>("/returns-out", { ...values, lines: values.lines.map(toLinePayload) })).data,
    onSuccess: (doc) => {
      message.success(`Created return to supplier ${doc.doc_no}; post it once the goods are handed over`);
      queryClient.invalidateQueries({ queryKey: ["returns-out"] });
      navigate(`/returns-out/${doc.id}`);
    },
    onError: showError,
  });

  return (
    <Card title="New return to supplier">
      <Form form={form} layout="vertical" initialValues={{ lines: [{}] }} onKeyDown={preventEnterSubmit} onFinish={(v) => save.mutate(v)}>
        <Space size="large" wrap>
          <Form.Item name="partner_id" label="Supplier" rules={[{ required: true }]}>
            <SupplierSelect style={{ width: 260 }} />
          </Form.Item>
          <Form.Item name="reason_code_id" label="Return reason" rules={[{ required: true }]}>
            <ReasonSelect category="RETURN" style={{ width: 220 }} />
          </Form.Item>
          <Form.Item name="remark" label="Remark">
            <Input style={{ width: 320 }} maxLength={400} />
          </Form.Item>
        </Space>
        <StockLinesEditor form={form} name="lines" locationLabel="From location" />
        <FormFooter>
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            Create return to supplier
          </Button>
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
