import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Space, Switch, Table, message } from "antd";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";

interface Feature {
  code: string;
  name: string;
  description: string;
  enabled: boolean;
}

/** Switch extension modules per the company's needs: when off, menus are hidden and the API rejects calls; existing data is kept */
export default function FeaturesPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["features"],
    queryFn: async () => (await apiClient.get<Feature[]>("/features")).data,
  });

  const toggle = useMutation({
    mutationFn: async ({ code, enabled }: { code: string; enabled: boolean }) =>
      (await apiClient.put<Feature>(`/features/${code}`, { enabled })).data,
    onSuccess: (feature) => {
      message.success(`${feature.name} ${feature.enabled ? "enabled" : "disabled"}`);
      // Write the result straight into the cache: if the switch still showed the old value while the list refetches, another click would submit the same value
      queryClient.setQueryData<Feature[]>(["features"], (old) => old?.map((f) => (f.code === feature.code ? feature : f)));
      // The menu follows the feature list in /auth/me, refresh it now
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: showError,
  });

  return (
    <Space orientation="vertical" style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        title="Enable the modules your business needs. When a module is off its menus are hidden and the API rejects calls; data already created is kept and usable again once re-enabled."
      />
      <Table<Feature>
        rowKey="code"
        loading={isLoading}
        dataSource={data}
        pagination={false}
        columns={[
          { title: "Feature", dataIndex: "name", width: 160 },
          { title: "Description", dataIndex: "description" },
          {
            title: "Enabled",
            width: 100,
            render: (_, f) => (
              <Switch
                checked={f.enabled}
                loading={toggle.isPending && toggle.variables?.code === f.code}
                disabled={toggle.isPending}
                onChange={(enabled) => toggle.mutate({ code: f.code, enabled })}
                data-testid={`feature-${f.code}`}
              />
            ),
          },
        ]}
      />
    </Space>
  );
}
