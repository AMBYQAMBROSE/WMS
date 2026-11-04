import { useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Input, Modal, Select, Space, Switch, Table, Tag, message } from "antd";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { useCan, useMe } from "@/api/me";

interface RoleBrief {
  id: string;
  code: string;
  name: string;
}

interface User {
  id: string;
  username: string;
  display_name: string;
  email: string | null;
  is_active: boolean;
  roles: RoleBrief[];
}

interface UserForm {
  username?: string;
  password?: string;
  display_name: string;
  email?: string;
  is_active: boolean;
  role_codes: string[];
}

export default function UsersPage() {
  const can = useCan();
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const [form] = Form.useForm<UserForm>();
  const [pwdForm] = Form.useForm<{ password: string }>();
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const [keyword, setKeyword] = useState("");

  const { data: users, isLoading } = useQuery({
    queryKey: ["users"],
    queryFn: async () => (await apiClient.get<User[]>("/users")).data,
  });
  const { data: roles = [] } = useQuery({
    queryKey: ["roles"],
    queryFn: async () => (await apiClient.get<RoleBrief[]>("/roles")).data,
    enabled: can("role.read"),
  });

  const save = useMutation({
    mutationFn: async (v: UserForm) =>
      editing === "new"
        ? apiClient.post("/users", v)
        : apiClient.put(`/users/${(editing as User).id}`, {
            display_name: v.display_name,
            email: v.email || null,
            is_active: v.is_active,
            role_codes: v.role_codes,
          }),
    onSuccess: () => {
      message.success("Saved; takes effect immediately");
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["roles"] });
      queryClient.invalidateQueries({ queryKey: ["me"] });
      setEditing(null);
    },
    onError: showError,
  });

  const reset = useMutation({
    mutationFn: async (v: { password: string }) => apiClient.post(`/users/${resetting!.id}/reset-password`, v),
    onSuccess: () => {
      message.success("Password reset");
      setResetting(null);
    },
    onError: showError,
  });

  const open = (user: User | "new") => setEditing(user);
  // The form unmounts when the modal closes (destroyOnHidden); initial values go through initialValues, never by calling form methods while unmounted
  const initialValues =
    editing === null || editing === "new"
      ? { username: "", password: "", display_name: "", email: "", is_active: true, role_codes: [] }
      : {
          display_name: editing.display_name,
          email: editing.email ?? "",
          is_active: editing.is_active,
          role_codes: editing.roles.map((r) => r.code),
        };

  const isNew = editing === "new";
  const isSelf = editing !== null && editing !== "new" && editing.id === me?.id;
  const kw = keyword.trim().toLowerCase();
  const shown = (users ?? []).filter(
    (u) => !kw || u.username.toLowerCase().includes(kw) || u.display_name.toLowerCase().includes(kw),
  );

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Space>
        {can("user.create") && (
          <Button type="primary" onClick={() => open("new")}>
            New user
          </Button>
        )}
        <Input.Search
          allowClear
          placeholder="Search by username/name"
          style={{ width: 240 }}
          onChange={(e) => setKeyword(e.target.value)}
          data-testid="user-search"
        />
      </Space>
      <Table<User>
        rowKey="id"
        loading={isLoading}
        dataSource={shown}
        columns={[
          { title: "Username", dataIndex: "username" },
          { title: "Name", dataIndex: "display_name" },
          { title: "Email", dataIndex: "email" },
          { title: "Roles", render: (_, u) => u.roles.map((r) => <Tag key={r.id}>{r.name}</Tag>) },
          {
            title: "Status",
            dataIndex: "is_active",
            render: (v: boolean) => (v ? <Tag color="green">Active</Tag> : <Tag color="red">Disabled</Tag>),
          },
          {
            title: "Actions",
            render: (_, u) =>
              can("user.update") && (
                <Space>
                  <Button size="small" onClick={() => open(u)}>
                    Edit
                  </Button>
                  <Button
                    size="small"
                    onClick={() => setResetting(u)}
                  >
                    Reset password
                  </Button>
                </Space>
              ),
          },
        ]}
      />

      <Modal
        open={editing !== null}
        title={editing === "new" ? "New user" : `Edit user: ${editing?.username ?? ""}`}
        onCancel={() => setEditing(null)}
        onOk={() => form.submit()}
        confirmLoading={save.isPending}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" preserve={false} initialValues={initialValues} onFinish={(v) => save.mutate(v)}>
          {isNew && (
            <>
              <Form.Item name="username" label="Username" rules={[{ required: true }]}>
                <Input maxLength={100} autoComplete="off" />
              </Form.Item>
              <Form.Item name="password" label="Initial password" rules={[{ required: true, min: 6, message: "At least 6 characters" }]}>
                <Input.Password autoComplete="new-password" />
              </Form.Item>
            </>
          )}
          <Form.Item name="display_name" label="Name" rules={[{ required: true }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item name="email" label="Email">
            <Input maxLength={200} />
          </Form.Item>
          <Form.Item name="role_codes" label="Roles">
            <Select mode="multiple" optionFilterProp="label" options={roles.map((r) => ({ value: r.code, label: r.name }))} />
          </Form.Item>
          {!isNew && (
            <Form.Item
              name="is_active"
              label="Active"
              valuePropName="checked"
              extra={isSelf ? "You cannot deactivate your own account" : "A deactivated account can no longer do anything, effective immediately"}
            >
              <Switch disabled={isSelf} />
            </Form.Item>
          )}
        </Form>
      </Modal>

      <Modal
        open={resetting !== null}
        title={`Reset password: ${resetting?.username ?? ""}`}
        onCancel={() => setResetting(null)}
        onOk={() => pwdForm.submit()}
        confirmLoading={reset.isPending}
        destroyOnHidden
      >
        <Form form={pwdForm} layout="vertical" preserve={false} onFinish={(v) => reset.mutate(v)}>
          <Form.Item name="password" label="New password" rules={[{ required: true, min: 6, message: "At least 6 characters" }]}>
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
