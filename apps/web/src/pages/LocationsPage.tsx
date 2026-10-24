import { useQuery } from "@tanstack/react-query";
import { Table } from "antd";

import { apiClient } from "@/api/client";

interface Location {
  id: string;
  code: string;
  name: string;
  location_type: string;
  path: string;
  is_pickable: boolean;
}

export default function LocationsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["locations"],
    queryFn: async () => {
      const response = await apiClient.get<Location[]>("/locations");
      return response.data;
    },
  });

  return (
    <Table<Location>
      rowKey="id"
      loading={isLoading}
      dataSource={data}
      columns={[
        { title: "编码", dataIndex: "code" },
        { title: "名称", dataIndex: "name" },
        { title: "类型", dataIndex: "location_type" },
        { title: "路径", dataIndex: "path" },
        { title: "可拣货", dataIndex: "is_pickable", render: (v: boolean) => (v ? "是" : "否") },
      ]}
    />
  );
}
