import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, message } from "antd";
import type { Dayjs } from "dayjs";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import StockLinesEditor, { toLinePayload } from "@/components/StockLinesEditor";
import { preventEnterSubmit } from "@/components/documents";
import { FormFooter, FormSection, useUnsavedChanges } from "@/components/ui";

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
  const unsaved = useUnsavedChanges();

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
      unsaved.reset();
      message.success(`Created repack ${doc.doc_no}; post it once the work is done`);
      queryClient.invalidateQueries({ queryKey: ["repacks"] });
      navigate(`/repacks/${doc.id}`);
    },
    onError: showError,
  });

  return (
    <Card title="New repack">
      <Form
        form={form}
        layout="vertical"
        initialValues={{ inputs: [{}], outputs: [{}] }}
        onKeyDown={preventEnterSubmit}
        onFinish={(v) => save.mutate(v)}
        {...unsaved.formProps}
      >
        <FormSection
          title="Details"
          description="Unpacking, kitting, repackaging: posting deducts “Consumed” and adds “Produced” in one transaction; if any line is short, nothing takes effect."
        >
          <Form.Item name="remark" label="Remark" style={{ maxWidth: 520 }}>
            <Input maxLength={400} placeholder="Optional" />
          </Form.Item>
        </FormSection>
        <FormSection title="Consumed" description="Items taken out of stock.">
          <StockLinesEditor form={form} name="inputs" locationLabel="From location" testId="repack-inputs" />
        </FormSection>
        <FormSection title="Produced" description="Items that come out of the work.">
          <StockLinesEditor form={form} name="outputs" locationLabel="To location" testId="repack-outputs" />
        </FormSection>
        <FormFooter note="Created as a draft; post it once the work is done">
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            Create repack
          </Button>
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
