import { DeleteOutlined, EditOutlined } from "@ant-design/icons";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Popconfirm, Space, message } from "antd";
import type { TableColumnType } from "antd";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";

interface Options<T> {
  /** Permission prefix, e.g. "item": Edit needs item.update, Delete needs item.delete */
  permission: string;
  /** API collection path, e.g. "/items"; DELETE goes to {path}/{id} */
  path: string;
  queryKey: string;
  /** What the record is called in the buttons and the confirmation, e.g. "item A1007" */
  describe: (record: T) => string;
  onEdit: (record: T) => void;
}

/** Edit / Delete column for master data lists; each button only shows with its permission, and no column at all without either */
export function useMasterActionsColumn<T extends { id: string }>({
  permission,
  path,
  queryKey,
  describe,
  onEdit,
}: Options<T>): TableColumnType<T> | null {
  const can = useCan();
  const queryClient = useQueryClient();
  const canEdit = can(`${permission}.update`);
  const canDelete = can(`${permission}.delete`);
  const remove = useMutation({
    mutationFn: (record: T) => apiClient.delete(`${path}/${record.id}`),
    onSuccess: () => {
      message.success("Deleted");
      queryClient.invalidateQueries({ queryKey: [queryKey] });
    },
    onError: showError,
  });

  if (!canEdit && !canDelete) return null;
  return {
    title: "Actions",
    key: "actions",
    fixed: "right",
    render: (_: unknown, record: T) => (
      <Space size={4}>
        {canEdit && (
          <Button size="small" type="text" icon={<EditOutlined />} onClick={() => onEdit(record)} aria-label={`Edit ${describe(record)}`}>
            Edit
          </Button>
        )}
        {canDelete && (
          <Popconfirm
            title={`Delete ${describe(record)}?`}
            description="It is permanently removed. Refused if stock, documents or users still refer to it; set it inactive instead."
            okText="Delete"
            okButtonProps={{ danger: true }}
            onConfirm={() => remove.mutateAsync(record).catch(() => undefined)}
          >
            <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label={`Delete ${describe(record)}`}>
              Delete
            </Button>
          </Popconfirm>
        )}
      </Space>
    ),
  };
}
