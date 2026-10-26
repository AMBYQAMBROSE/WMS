import { Button, Layout, Menu } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "@/stores/authStore";

const { Header, Sider, Content } = Layout;

const menuItems = [
  {
    key: "inbound",
    label: "入库",
    children: [
      { key: "/purchase-orders", label: "采购单" },
      { key: "/grns", label: "收货单" },
      { key: "/putaways", label: "上架单" },
    ],
  },
  {
    key: "inventory",
    label: "库存",
    children: [{ key: "/stock", label: "库存查询" }],
  },
  {
    key: "master",
    label: "主数据",
    children: [
      { key: "/business-partners", label: "业务伙伴" },
      { key: "/items", label: "商品" },
      { key: "/locations", label: "仓位" },
    ],
  },
];

export default function MainLayout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const logout = useAuthStore((state) => state.logout);
  const selected = "/" + pathname.split("/")[1];

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider>
        <div style={{ color: "#fff", fontSize: 18, fontWeight: 600, padding: 16 }}>WMS</div>
        <Menu
          theme="dark"
          mode="inline"
          items={menuItems}
          selectedKeys={[selected]}
          defaultOpenKeys={["inbound", "inventory", "master"]}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff", padding: "0 16px", display: "flex", justifyContent: "flex-end", alignItems: "center" }}>
          <Button onClick={logout}>退出登录</Button>
        </Header>
        <Content style={{ margin: 16 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
