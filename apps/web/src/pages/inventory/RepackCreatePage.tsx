import { useRef } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, message } from "antd";
import type { Dayjs } from "dayjs";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Document } from "@/api/types";
import StockLinesEditor, { toLinePayload } from "@/components/StockLinesEditor";
import { CreateButtons, announcePosted, postDraft, preventEnterSubmit } from "@/components/documents";
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

  const postNow = useRef(false);

  const save = useMutation({
    mutationFn: async (values: FormValues) => {
      const draft = (
        await apiClient.post<Document>("/repacks", {
          remark: values.remark,
          inputs: values.inputs.map(toLinePayload),
          outputs: values.outputs.map(toLinePayload),
        })
      ).data;
      return postNow.current ? postDraft("repacks", draft) : { doc: draft, posted: false };
    },
    onSuccess: ({ doc, posted }) => {
      unsaved.reset();
      if (posted) announcePosted(doc);
      else if (!postNow.current) message.success(`Created repack ${doc.doc_no}; post it once the work is done`);
      queryClient.invalidateQueries({ queryKey: ["repacks"] });
      queryClient.invalidateQueries({ queryKey: ["stock"] });
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
        <FormSection title="Consumed" description="Items taken out of stock. Choose the location first: its item, batch and free quantity are filled in.">
          <StockLinesEditor form={form} name="inputs" locationLabel="From location" testId="repack-inputs" stockSource />
        </FormSection>
        <FormSection title="Produced" description="Items that come out of the work.">
          <StockLinesEditor form={form} name="outputs" locationLabel="To location" testId="repack-outputs" />
        </FormSection>
        <FormFooter note="Post once the work is done: posting changes the stock">
          <CreateButtons label="Create repack" postPerm="repack.post" postNow={postNow} loading={save.isPending} />
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
