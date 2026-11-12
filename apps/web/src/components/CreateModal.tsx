import type { ReactNode } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Form, Modal, message } from "antd";
import type { FormInstance } from "antd";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";

interface Props<T> {
  open: boolean;
  title: string;
  path: string;
  queryKey: string;
  initialValues?: Partial<T>;
  /** When set, the modal edits this record (PUT {path}/{id} with its row_version) instead of creating one */
  record?: { id: string; row_version: number } | null;
  onClose: () => void;
  children: (form: FormInstance<T>) => ReactNode;
}

/** Cleared inputs come back as undefined, which JSON drops; send null so the field is actually cleared */
const clearedAsNull = (values: object) =>
  Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v === undefined || v === "" ? null : v]));

export default function CreateModal<T extends object>({
  open,
  title,
  path,
  queryKey,
  initialValues,
  record,
  onClose,
  children,
}: Props<T>) {
  const [form] = Form.useForm<T>();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (values: T): Promise<unknown> =>
      record
        ? apiClient.put(`${path}/${record.id}`, { ...clearedAsNull(values), row_version: record.row_version })
        : apiClient.post(path, values),
    onSuccess: () => {
      message.success(record ? "Saved" : "Created");
      queryClient.invalidateQueries({ queryKey: [queryKey] });
      form.resetFields();
      onClose();
    },
    onError: showError,
  });

  return (
    <Modal
      open={open}
      title={title}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={mutation.isPending}
      destroyOnHidden
    >
      {/* preserve={false}: values from one record must not leak into the next one opened */}
      <Form form={form} layout="vertical" preserve={false} initialValues={initialValues} onFinish={(v) => mutation.mutate(v)}>
        {children(form)}
      </Form>
    </Modal>
  );
}
