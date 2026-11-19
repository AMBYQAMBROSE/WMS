import { useRef } from "react";
import type { ReactNode, RefObject } from "react";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Form, Modal, message } from "antd";
import type { FormInstance, FormProps } from "antd";

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
  /** Reshape the form values before they are sent */
  transform?: (values: T) => object;
  children: (form: FormInstance<T>) => ReactNode;
}

/** Cleared inputs come back as undefined, which JSON drops; send null so the field is actually cleared */
const clearedAsNull = (values: object) =>
  Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v === undefined || v === "" ? null : v]));

/**
 * The form inside a modal with destroyOnHidden. It owns its form instance, so each opening gets a fresh one that starts
 * from that record's initialValues alone; the modal's OK button submits it through `submitRef`.
 *
 * Why not one form instance on the modal: it outlives each opening, and leftover list values (an item's packing rows)
 * were merged over the next record's initialValues. Clearing it on unmount (clearOnDestroy) also fires during React
 * StrictMode's mount-unmount-mount and left every edit form empty in development. And no preserve={false}: with it,
 * unmounting a Form.List row sets its values to undefined, so that same practice unmount emptied list rows.
 */
export function ModalForm<T extends object>({
  submitRef,
  children,
  ...props
}: Omit<FormProps<T>, "form" | "children"> & {
  submitRef: RefObject<(() => void) | null>;
  children: ReactNode | ((form: FormInstance<T>) => ReactNode);
}) {
  const [form] = Form.useForm<T>();
  submitRef.current = () => form.submit();
  return (
    <Form<T> form={form} layout="vertical" {...props}>
      {typeof children === "function" ? children(form) : children}
    </Form>
  );
}

export default function CreateModal<T extends object>({
  open,
  title,
  path,
  queryKey,
  initialValues,
  record,
  onClose,
  transform,
  children,
}: Props<T>) {
  const submitRef = useRef<(() => void) | null>(null);
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (formValues: T): Promise<unknown> => {
      const values = transform ? transform(formValues) : formValues;
      return record
        ? apiClient.put(`${path}/${record.id}`, { ...clearedAsNull(values), row_version: record.row_version })
        : apiClient.post(path, values);
    },
    onSuccess: () => {
      message.success(record ? "Saved" : "Created");
      queryClient.invalidateQueries({ queryKey: [queryKey] });
      onClose();
    },
    onError: showError,
  });

  return (
    <Modal
      open={open}
      title={title}
      onCancel={onClose}
      onOk={() => submitRef.current?.()}
      confirmLoading={mutation.isPending}
      destroyOnHidden
    >
      <ModalForm<T> submitRef={submitRef} initialValues={initialValues} onFinish={(v) => mutation.mutate(v)}>
        {children}
      </ModalForm>
    </Modal>
  );
}
