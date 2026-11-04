import { useState } from "react";

import { BarcodeOutlined, LockOutlined, MoonOutlined, NodeIndexOutlined, SunOutlined, ThunderboltOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, Button, Form, Input, Typography } from "antd";
import { useNavigate } from "react-router";

import { apiClient } from "@/api/client";
import { BrandMark } from "@/components/ui";
import { useAuthStore } from "@/stores/authStore";
import { useUiStore } from "@/stores/uiStore";

interface LoginFormValues {
  username: string;
  password: string;
}

const FEATURES = [
  { icon: <BarcodeOutlined />, title: "Scan-first operations", text: "Receive, put away, pick and count with barcode scanners and PDAs." },
  { icon: <NodeIndexOutlined />, title: "Every unit traceable", text: "Batch, expiry and bin-level ledger for each movement." },
  { icon: <ThunderboltOutlined />, title: "Live visibility", text: "Backlog, shortages and stock health update in real time." },
];

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const navigate = useNavigate();
  const setToken = useAuthStore((state) => state.setToken);
  const { mode, toggleMode } = useUiStore();

  const onFinish = async (values: LoginFormValues) => {
    setLoading(true);
    setFailed(false);
    try {
      const form = new URLSearchParams();
      form.set("username", values.username);
      form.set("password", values.password);
      const response = await apiClient.post("/auth/login", form, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });
      setToken(response.data.access_token);
      navigate("/");
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="wms-login">
      <aside className="wms-login-art">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <BrandMark size={40} />
          <div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>WMS</div>
            <div style={{ fontSize: 12, opacity: 0.6, letterSpacing: 0.4, textTransform: "uppercase" }}>Warehouse cloud</div>
          </div>
        </div>

        <div style={{ maxWidth: 600 }}>
          <h1 style={{ fontSize: 40, lineHeight: 1.15, fontWeight: 700, letterSpacing: -1, margin: "0 0 16px" }}>
            Run every dock, aisle and&nbsp;bin
            <span style={{ display: "block", background: "linear-gradient(90deg,#a5b4fc,#67e8f9)", WebkitBackgroundClip: "text", color: "transparent" }}>
              from one place.
            </span>
          </h1>
          <p style={{ fontSize: 16, opacity: 0.7, margin: "0 0 36px", lineHeight: 1.6 }}>
            Inbound, outbound, inventory and returns — connected end to end.
          </p>
          <div style={{ display: "grid", gap: 20 }}>
            {FEATURES.map((f) => (
              <div key={f.title} className="wms-login-feature">
                <span className="wms-login-feature-icon">{f.icon}</span>
                <div>
                  <div style={{ fontWeight: 600, marginBottom: 2 }}>{f.title}</div>
                  <div style={{ opacity: 0.6, fontSize: 14 }}>{f.text}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ fontSize: 12, opacity: 0.45 }}>© {new Date().getFullYear()} WMS</div>
      </aside>

      <main className="wms-login-form" style={{ position: "relative" }}>
        <Button
          shape="circle"
          type="text"
          icon={mode === "dark" ? <SunOutlined /> : <MoonOutlined />}
          onClick={toggleMode}
          aria-label="Toggle color mode"
          style={{ position: "absolute", top: 24, right: 24 }}
        />
        <div style={{ width: "100%", maxWidth: 380 }}>
          <Typography.Title level={2} style={{ marginBottom: 6, fontWeight: 700, letterSpacing: -0.5 }}>
            Welcome back
          </Typography.Title>
          <Typography.Paragraph type="secondary" style={{ marginBottom: 32 }}>
            Sign in to your warehouse workspace.
          </Typography.Paragraph>

          {failed && <Alert type="error" showIcon title="Incorrect username or password" style={{ marginBottom: 20 }} />}

          <Form onFinish={onFinish} layout="vertical" requiredMark={false} size="large">
            <Form.Item name="username" label="Username" rules={[{ required: true, message: "Enter your username" }]}>
              <Input prefix={<UserOutlined style={{ color: "var(--ant-color-text-quaternary)" }} />} autoComplete="username" autoFocus />
            </Form.Item>
            <Form.Item name="password" label="Password" rules={[{ required: true, message: "Enter your password" }]}>
              <Input.Password prefix={<LockOutlined style={{ color: "var(--ant-color-text-quaternary)" }} />} autoComplete="current-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={loading} style={{ marginTop: 8, height: 46 }}>
              Sign in
            </Button>
          </Form>
        </div>
      </main>
    </div>
  );
}
