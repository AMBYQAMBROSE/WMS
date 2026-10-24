import { useQuery } from "@tanstack/react-query";
import { Table } from "antd";

import { apiClient } from "@/api/client";

interface Item {
  id: string;
  sku_code: string;
  name: string;
  category: string | null;
  is_active: boolean;
}

export default function ItemsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["items"],
    queryFn: async () => {
      const response = await apiClient.get<Item[]>("/items");
      return response.data;
    },
  });

  return (
    <Table<Item>
      rowKey="id"
      loading={isLoading}
      dataSource={data}
      columns={[
        { title: "SKU", dataIndex: "sku_code" },
        { title: "名称", dataIndex: "name" },
        { title: "分类", dataIndex: "category" },
        { title: "启用", dataIndex: "is_active", render: (v: boolean) => (v ? "是" : "否") },
      ]}
    />
  );
}
