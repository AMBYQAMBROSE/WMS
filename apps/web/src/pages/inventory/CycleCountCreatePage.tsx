import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, message } from "antd";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { CycleCount } from "@/api/types";
import { preventEnterSubmit } from "@/components/documents";
import { LocationSelect } from "@/components/selects";
import { FormFooter, FormSection } from "@/components/ui";

interface FormValues {
  location_ids: string[];
  remark?: string;
}

export default function CycleCountCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const save = useMutation({
    mutationFn: async (values: FormValues) => (await apiClient.post<CycleCount>("/cycle-counts", values)).data,
    onSuccess: (doc) => {
      message.success(`Cycle count ${doc.doc_no} started; the selected locations are frozen`);
      queryClient.invalidateQueries({ queryKey: ["cycle-counts"] });
      navigate(`/cycle-counts/${doc.id}`);
    },
    onError: showError,
  });

  return (
    <Card title="Start cycle count">
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        title="The selected locations are frozen immediately (no receiving, putaway, moves or adjustments) until the count is posted or cancelled. Avoid peak hours."
      />
      <Form layout="vertical" onKeyDown={preventEnterSubmit} onFinish={(v: FormValues) => save.mutate(v)}>
        <FormSection title="Scope" description="Bins and docks to count. Empty locations can be counted too.">
          <Form.Item name="location_ids" label="Locations to count" rules={[{ required: true, message: "Choose at least one location" }]} style={{ maxWidth: 640 }}>
            <LocationSelect mode="multiple" types={["BIN", "DOCK"]} allowLocked style={{ width: "100%" }} placeholder="Multiple allowed, empty locations too" />
          </Form.Item>
          <Form.Item name="remark" label="Remark" style={{ maxWidth: 640 }}>
            <Input maxLength={400} placeholder="Optional" />
          </Form.Item>
        </FormSection>
        <FormFooter>
          <Button type="primary" htmlType="submit" loading={save.isPending}>
            Start count
          </Button>
          <Button onClick={() => navigate(-1)}>Cancel</Button>
        </FormFooter>
      </Form>
    </Card>
  );
}
