import { useQuery } from "@tanstack/react-query";
import { Table } from "antd";

import { apiClient } from "@/api/client";

interface BusinessPartner {
  id: string;
  code: string;
  name: string;
  partner_type: string;
  is_active: boolean;
}

export default function BusinessPartnersPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["business-partners"],
    queryFn: async () => {
      const response = await apiClient.get<BusinessPartner[]>("/business-partners");
      return response.data;
    },
  });

  return (
    <Table<BusinessPartner>
      rowKey="id"
      loading={isLoading}
      dataSource={data}
      columns={[
        { title: "编码", dataIndex: "code" },
        { title: "名称", dataIndex: "name" },
        { title: "类型", dataIndex: "partner_type" },
        { title: "启用", dataIndex: "is_active", render: (v: boolean) => (v ? "是" : "否") },
      ]}
    />
  );
}
