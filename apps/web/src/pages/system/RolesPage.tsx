import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Checkbox, Form, Input, Modal, Popconfirm, Space, Table, Tag, message } from "antd";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan } from "@/api/me";
import type { components } from "@/api/schema";
import { PERMISSION_MODULE_LABELS } from "@/constants/labels";

type Schemas = components["schemas"];

type Permission = Schemas["PermissionRead"];
type Role = Schemas["RoleRead"];

interface RoleForm {
  code: string;
  name: string;
  permission_codes: string[];
}

/** Permission checkboxes grouped by module, each group with "select all" */
function PermissionPicker({
  permissions,
  value = [],
  onChange,
  disabled,
}: {
  permissions: Permission[];
  value?: string[];
  onChange?: (v: string[]) => void;
  disabled?: boolean;
}) {
  const modules = [...new Set(permissions.map((p) => p.module))];
  const selected = new Set(value);
  const setModule = (module: string, codes: string[]) => {
    const others = value.filter((c) => permissions.find((p) => p.code === c)?.module !== module);
    onChange?.([...others, ...codes]);
  };
  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      {modules.map((module) => {
        const items = permissions.filter((p) => p.module === module);
        const checked = items.filter((p) => selected.has(p.code)).map((p) => p.code);
        return (
          <Card
            key={module}
            size="small"
            title={
              <Checkbox
                disabled={disabled}
                checked={checked.length === items.length}
                indeterminate={checked.length > 0 && checked.length < items.length}
                onChange={(e) => setModule(module, e.target.checked ? items.map((p) => p.code) : [])}
              >
                {PERMISSION_MODULE_LABELS[module] ?? module}
              </Checkbox>
            }
          >
            <Checkbox.Group
              disabled={disabled}
              value={checked}
              onChange={(codes) => setModule(module, codes as string[])}
              options={items.map((p) => ({ value: p.code, label: p.description }))}
            />
          </Card>
        );
      })}
    </Space>
  );
}

export default function RolesPage() {
  const can = useCan();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<RoleForm>();
  const [editing, setEditing] = useState<Role | "new" | null>(null);

  const { data: roles, isLoading } = useQuery({
    queryKey: ["roles"],
    queryFn: async () => (await apiClient.get<Role[]>("/roles")).data,
  });
  const { data: permissions = [] } = useQuery({
    queryKey: ["permissions"],
    queryFn: async () => (await apiClient.get<Permission[]>("/permissions")).data,
  });

  const done = (text: string) => {
    message.success(text);
    queryClient.invalidateQueries({ queryKey: ["roles"] });
    queryClient.invalidateQueries({ queryKey: ["me"] });
    setEditing(null);
  };

  const save = useMutation({
    mutationFn: async (values: RoleForm) =>
      editing === "new"
        ? apiClient.post("/roles", values)
        : apiClient.put(`/roles/${(editing as Role).id}`, {
            name: values.name,
            permission_codes: values.permission_codes,
            row_version: (editing as Role).row_version,
          }),
    onSuccess: () => done("Saved; permissions take effect immediately"),
    onError: showError,
  });

  const remove = useMutation({
    mutationFn: async (role: Role) => apiClient.delete(`/roles/${role.id}`),
    onSuccess: () => done("Deleted"),
    onError: showError,
  });

  const open = (role: Role | "new") => {
    setEditing(role);
    form.setFieldsValue(
      role === "new" ? { code: "", name: "", permission_codes: [] } : { code: role.code, name: role.name, permission_codes: role.permission_codes },
    );
  };

  const editingSystem = editing !== null && editing !== "new" && editing.is_system;

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      {can("role.create") && (
        <Button type="primary" onClick={() => open("new")}>
          New role
        </Button>
      )}
      <Table<Role>
        rowKey="id"
        loading={isLoading}
        dataSource={roles}
        pagination={false}
        columns={[
          { title: "Code", dataIndex: "code" },
          {
            title: "Name",
            render: (_, r) => (
              <Space>
                {r.name}
                {r.is_system && <Tag color="gold">System</Tag>}
              </Space>
            ),
          },
          { title: "Permissions", render: (_, r) => r.permission_codes.length },
          { title: "Users", dataIndex: "user_count" },
          {
            title: "Actions",
            render: (_, r) => (
              <Space>
                <Button size="small" onClick={() => open(r)}>
                  {can("role.update") ? "Edit" : "View"}
                </Button>
                {can("role.delete") && !r.is_system && (
                  <Popconfirm title={`Delete role ${r.name}?`} onConfirm={() => remove.mutate(r)}>
                    <Button size="small" danger disabled={r.user_count > 0}>
                      Delete
                    </Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />
      <Modal
        open={editing !== null}
        width={860}
        title={editing === "new" ? "New role" : `Role: ${editing?.name ?? ""}`}
        onCancel={() => setEditing(null)}
        onOk={() => form.submit()}
        okButtonProps={{ disabled: !can(editing === "new" ? "role.create" : "role.update") }}
        confirmLoading={save.isPending}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Space size="large">
            <Form.Item name="code" label="Code" rules={[{ required: true }]}>
              <Input disabled={editing !== "new"} maxLength={50} />
            </Form.Item>
            <Form.Item name="name" label="Name" rules={[{ required: true }]}>
              <Input maxLength={100} />
            </Form.Item>
          </Space>
          {editingSystem && <p style={{ color: "var(--ant-color-text-tertiary)" }}>The system role always has every permission; its permissions cannot be changed.</p>}
          <Form.Item name="permission_codes" label="Permissions">
            <PermissionPicker permissions={permissions} disabled={editingSystem || !can("role.update")} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
