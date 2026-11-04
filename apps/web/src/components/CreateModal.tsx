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
  onClose: () => void;
  children: (form: FormInstance<T>) => ReactNode;
}

export default function CreateModal<T extends object>({
  open,
  title,
  path,
  queryKey,
  initialValues,
  onClose,
  children,
}: Props<T>) {
  const [form] = Form.useForm<T>();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (values: T) => apiClient.post(path, values),
    onSuccess: () => {
      message.success("Created");
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
      <Form form={form} layout="vertical" initialValues={initialValues} onFinish={(v) => mutation.mutate(v)}>
        {children(form)}
      </Form>
    </Modal>
  );
}
