import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, Typography, message } from "antd";
import type { Dayjs } from "dayjs";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import StockLinesEditor, { toLinePayload } from "@/components/StockLinesEditor";
import { preventEnterSubmit } from "@/components/documents";
import { FormFooter } from "@/components/ui";

type Line = { item_id?: string; uom_id?: string; qty?: number; location_id?: string; batch_no?: string; expiry_date?: Dayjs };

interface FormValues {
  remark?: string;
  inputs: Line[];
  outputs: Line[];
}

export default function RepackCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<FormValues>();

  const save = useMutation({
    mutationFn: async (values: FormValues) =>
      (
        await apiClient.post<Document>("/repacks", {
          remark: values.remark,
          inputs: values.inputs.map(toLinePayload),
          outputs: values.outputs.map(toLinePayload),
        })
      ).data,
    onSuccess: (doc) => {
      message.success(`Created repack ${doc.doc_no}; post it once the work is done`);
      queryClient.invalidateQueries({ queryKey: ["repacks"] });
      navigate(`/repacks/${doc.id}`);
    },
    onError: showError,
  });

  return (
    <Card title="New repack">
      <Typography.Paragraph type="secondary">
        Unpacking, kitting, repackaging: posting deducts "Consumed" and adds "Produced" in one transaction; if any line is short, nothing takes effect.
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        initialValues={{ inputs: [{}], outputs: [{}] }}
        onKeyDown={preventEnterSubmit}
        onFinish={(v) => save.mutate(v)}
      >
        <Form.Item name="remark" label="Remark">
          <Input style={{ width: 400 }} maxLength={400} />
        </Form.Item>
        <Typography.Title level={5}>Consumed</Typography.Title>
        <StockLinesEditor form={form} name="inputs" locationLabel="From location" testId="repack-inputs" />
        <Typography.Title level={5} style={{ marginTop: 24 }}>
          Produced
        </Typography.Title>
        <StockLinesEditor form={form} name="outputs" locationLabel="To location" testId="repack-outputs" />
        <FormFooter>
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            Create repack
          </Button>
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
