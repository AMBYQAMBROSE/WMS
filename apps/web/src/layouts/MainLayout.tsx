import { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  AppstoreOutlined,
  ArrowLeftOutlined,
  BarChartOutlined,
  DatabaseOutlined,
  DownloadOutlined,
  EnterOutlined,
  ExportOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MoonOutlined,
  RollbackOutlined,
  SearchOutlined,
  SettingOutlined,
  SunOutlined,
} from "@ant-design/icons";
import { useQueryClient } from "@tanstack/react-query";
import { Avatar, Breadcrumb, Button, Dropdown, Input, Layout, Menu, Modal, Spin, Tooltip, Typography, type InputRef } from "antd";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router";

import { useCan, useFeature, useMe } from "@/api/me";
import { BrandMark, EmptyState, PageHeader } from "@/components/ui";
import { useLiveStore, useLiveUpdates, type LiveStatus } from "@/api/live";
import { useAuthStore } from "@/stores/authStore";
import { useUiStore } from "@/stores/uiStore";

const { Header, Sider, Content } = Layout;

interface MenuEntry {
  key: string;
  label: string;
  /** One-line description shown under the page title */
  description?: string;
  /** Permission needed to see the menu entry (usually the list's read permission); an array means any one of them */
  perm: string | string[];
  /** Feature flag the tenant must enable; omitted means a core feature that is always available */
  feature?: string;
}

interface MenuGroup {
  key: string;
  label: string;
  icon: ReactNode;
  children: MenuEntry[];
}

const MENU: MenuGroup[] = [
  {
    key: "reports",
    label: "Dashboard & reports",
    icon: <BarChartOutlined />,
    children: [
      { key: "/dashboard", label: "Dashboard", description: "Today's activity, open work and stock health at a glance", perm: "report.read" },
      { key: "/reports/turnover", label: "Stock turnover", description: "Opening, inbound, outbound and closing quantities per item", perm: "report.read" },
      { key: "/reports/picker-kpi", label: "Picker performance", description: "Lines and quantities picked per operator", perm: "report.read" },
      { key: "/reports/expiry", label: "Expiring stock", description: "Expired batches and those approaching their expiry date", perm: "report.read" },
      { key: "/reports/partner-ledger", label: "Partner ledger", description: "Quantities received from and shipped to each partner", perm: "report.read" },
    ],
  },
  {
    key: "inbound",
    label: "Inbound",
    icon: <DownloadOutlined />,
    children: [
      { key: "/purchase-orders", label: "Purchase orders", description: "Plan what suppliers will deliver", perm: "purchase_order.read" },
      { key: "/grns", label: "Goods receipts", description: "Record goods arriving at the dock", perm: "grn.read" },
      { key: "/putaways", label: "Putaways", description: "Move received goods into storage bins", perm: "putaway.read" },
    ],
  },
  {
    key: "outbound",
    label: "Outbound",
    icon: <ExportOutlined />,
    children: [
      { key: "/sales-orders", label: "Sales orders", description: "Customer orders from allocation to shipment", perm: "sales_order.read" },
      { key: "/picks", label: "Pick lists", description: "Picking tasks in bin order", perm: "pick.read" },
      { key: "/shipments", label: "Shipments", description: "Goods leaving the warehouse", perm: "shipment.read" },
      { key: "/shortages", label: "Shortages", description: "Order lines that could not be fully allocated", perm: "sales_order.read" },
    ],
  },
  {
    key: "inventory",
    label: "Inventory",
    icon: <DatabaseOutlined />,
    children: [
      { key: "/stock", label: "Stock", description: "Balances by item, location and batch, with the full ledger", perm: "stock.read" },
      { key: "/moves", label: "Moves", description: "Bin-to-bin transfers", perm: "move.read" },
      { key: "/adjustments", label: "Stock adjustments", description: "Correct quantities with a reason", perm: "adjustment.read" },
      { key: "/cycle-counts", label: "Cycle counts", description: "Count bins and reconcile differences", perm: "cycle_count.read" },
      { key: "/repacks", label: "Repacks", description: "Convert items into other items or packaging", perm: "repack.read", feature: "REPACK" },
    ],
  },
  {
    key: "returns",
    label: "Returns & assets",
    icon: <RollbackOutlined />,
    children: [
      { key: "/returns-in", label: "Customer returns", description: "Goods coming back from customers", perm: "return_in.read", feature: "RETURNS" },
      { key: "/returns-out", label: "Returns to supplier", description: "Goods sent back to suppliers", perm: "return_out.read", feature: "RETURNS" },
      { key: "/returnable-assets", label: "Returnable assets", description: "Pallets, crates and other assets held by partners", perm: "returnable_asset.read", feature: "RETURNABLE_ASSET" },
    ],
  },
  {
    key: "master",
    label: "Master data",
    icon: <AppstoreOutlined />,
    children: [
      { key: "/business-partners", label: "Business partners", description: "Suppliers and customers", perm: "business_partner.read" },
      { key: "/items", label: "Items", description: "SKUs, barcodes, units and tracking rules", perm: "item.read" },
      { key: "/locations", label: "Locations", description: "Warehouses, zones, racks and bins", perm: "location.read" },
      { key: "/reason-codes", label: "Reason codes", description: "Why stock was adjusted or returned", perm: "reason_code.read" },
    ],
  },
  {
    key: "system",
    label: "System",
    icon: <SettingOutlined />,
    children: [
      { key: "/users", label: "Users", description: "Accounts and their roles", perm: "user.read" },
      { key: "/roles", label: "Roles", description: "Permission sets assigned to users", perm: "role.read" },
      { key: "/features", label: "Feature flags", description: "Turn optional modules on or off for this tenant", perm: "system.settings" },
      { key: "/integration", label: "Integrations", description: "Webhook connectors and delivery history", perm: "integration.read" },
      { key: "/imports", label: "Data import", description: "Bulk-load master data and opening stock from spreadsheets", perm: ["item.create", "location.create", "business_partner.create", "adjustment.post"] },
      { key: "/audit-log", label: "Audit log", description: "Who changed what and when, with old and new values", perm: "audit.read" },
      { key: "/system-health", label: "System health", description: "Database, background worker, integration queue and monitoring", perm: "system.settings" },
    ],
  },
];

function useVisibleMenu() {
  const can = useCan();
  const hasFeature = useFeature();
  return MENU.map((group) => ({
    ...group,
    children: group.children.filter(
      (c) => (Array.isArray(c.perm) ? c.perm.some((p) => can(p)) : can(c.perm)) && hasFeature(c.feature),
    ),
  })).filter((group) => group.children.length > 0);
}

/** Route -> menu entry, group, and what kind of sub-page it is (list itself, new, edit, details) */
function useRouteMeta(pathname: string) {
  return useMemo(() => {
    let best: { group: MenuGroup; entry: MenuEntry } | undefined;
    for (const group of MENU) {
      for (const entry of group.children) {
        if ((pathname === entry.key || pathname.startsWith(entry.key + "/")) && (!best || entry.key.length > best.entry.key.length)) {
          best = { group, entry };
        }
      }
    }
    if (!best) return undefined;
    const rest = pathname.slice(best.entry.key.length);
    const sub = !rest || rest === "/" ? undefined : rest === "/new" ? "New" : rest.endsWith("/edit") ? "Edit" : "Details";
    return { ...best, sub };
  }, [pathname]);
}

/** Home after login: go to the first menu entry the user may see, so someone without purchasing rights does not land on a 403 */
export function HomeRedirect() {
  const { isLoading } = useMe();
  const menu = useVisibleMenu();
  if (isLoading) return <Spin style={{ margin: 48 }} />;
  const first = menu[0]?.children[0];
  if (!first) return <EmptyState title="No permissions assigned" hint="This account has no permissions yet. Please contact your administrator." />;
  return <Navigate to={first.key} replace />;
}

const initials = (name?: string) =>
  (name ?? "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("") || "?";

/** Ctrl/Cmd+K: jump to any page the user can open */
function QuickJump({ open, onClose, menu }: { open: boolean; onClose: () => void; menu: MenuGroup[] }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<InputRef>(null);
  const entries = menu.flatMap((g) => g.children.map((c) => ({ ...c, group: g })));
  const needle = q.trim().toLowerCase();
  const results = needle
    ? entries.filter((e) => `${e.label} ${e.group.label} ${e.description ?? ""}`.toLowerCase().includes(needle))
    : entries;

  useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
      setTimeout(() => input.current?.focus(), 50);
    }
  }, [open]);

  const go = (key: string) => {
    navigate(key);
    onClose();
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      closable={false}
      width={560}
      styles={{ container: { padding: 8 } }}
      destroyOnHidden
      afterOpenChange={(visible) => visible && input.current?.focus()}
    >
      <Input
        ref={input}
        autoFocus
        size="large"
        variant="borderless"
        prefix={<SearchOutlined style={{ color: "var(--ant-color-text-tertiary)", marginRight: 6 }} />}
        placeholder="Jump to a page…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setActive(0);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setActive((i) => Math.min(results.length - 1, i + 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setActive((i) => Math.max(0, i - 1));
          } else if (e.key === "Enter" && results[active]) {
            go(results[active].key);
          }
        }}
      />
      <div style={{ borderTop: "1px solid var(--wms-surface-border)", marginTop: 4, paddingTop: 6, maxHeight: 400, overflowY: "auto" }}>
        {results.length === 0 && <EmptyState title="No matching page" />}
        {results.map((e, i) => (
          <div
            key={e.key}
            onMouseEnter={() => setActive(i)}
            onClick={() => go(e.key)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "9px 12px",
              borderRadius: 8,
              cursor: "pointer",
              background: i === active ? "var(--ant-color-primary-bg)" : undefined,
            }}
          >
            <span style={{ color: i === active ? "var(--ant-color-primary)" : "var(--ant-color-text-tertiary)", fontSize: 16 }}>{e.group.icon}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 500 }}>{e.label}</div>
              <Typography.Text type="secondary" ellipsis style={{ fontSize: 12 }}>
                {e.group.label} · {e.description}
              </Typography.Text>
            </div>
            {i === active && <EnterOutlined style={{ color: "var(--ant-color-text-tertiary)" }} />}
          </div>
        ))}
      </div>
    </Modal>
  );
}

const LIVE_TEXT: Record<LiveStatus, { label: string; tip: string }> = {
  live: { label: "Live", tip: "Pages update by themselves as others change data" },
  connecting: { label: "Connecting", tip: "Connecting to live updates…" },
  offline: { label: "Offline", tip: "Live updates are paused; pages refresh when you reload or act. Reconnecting automatically." },
};

/** Live updates state: a dot plus a word, so it never depends on color alone */
function LiveIndicator() {
  const status = useLiveStore((s) => s.status);
  const text = LIVE_TEXT[status];
  return (
    <Tooltip title={text.tip}>
      <span className={`wms-live wms-live-${status}`} role="status" aria-label={`Live updates: ${text.label}`}>
        <span className="wms-live-dot" />
        {text.label}
      </span>
    </Tooltip>
  );
}

export default function MainLayout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const queryClient = useQueryClient();
  const logout = useAuthStore((state) => state.logout);
  const { mode, toggleMode, siderCollapsed, setSiderCollapsed } = useUiStore();
  const { data: me } = useMe();
  const menu = useVisibleMenu();
  const meta = useRouteMeta(pathname);
  const [openKeys, setOpenKeys] = useState<string[]>(meta ? [meta.group.key] : []);
  const [jumpOpen, setJumpOpen] = useState(false);
  useLiveUpdates();

  // Keep the current route's group expanded when navigating from elsewhere (quick jump, links in tables)
  useEffect(() => {
    if (meta && !openKeys.includes(meta.group.key)) setOpenKeys((keys) => [...keys, meta.group.key]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta?.group.key]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setJumpOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    document.title = meta ? `${meta.sub ? `${meta.sub} · ` : ""}${meta.entry.label} · WMS` : "WMS";
  }, [meta]);

  const doLogout = () => {
    logout();
    // After switching accounts the previous user's cached data must not be visible
    queryClient.clear();
  };

  const isMac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        className="wms-sider"
        width={256}
        collapsedWidth={72}
        collapsible
        collapsed={siderCollapsed}
        onCollapse={setSiderCollapsed}
        breakpoint="lg"
        trigger={null}
      >
        <Link to="/" className="wms-brand" style={siderCollapsed ? { padding: "0 19px" } : undefined}>
          <BrandMark />
          {!siderCollapsed && (
            <div>
              <div className="wms-brand-name">WMS</div>
              <div className="wms-brand-sub">Warehouse cloud</div>
            </div>
          )}
        </Link>
        <Menu
          className="wms-sider-menu"
          theme="dark"
          mode="inline"
          inlineIndent={16}
          items={menu.map(({ key, label, icon, children }) => ({
            key,
            label,
            icon,
            children: children.map(({ key: k, label: l }) => ({ key: k, label: l })),
          }))}
          selectedKeys={meta ? [meta.entry.key] : []}
          {...(siderCollapsed ? {} : { openKeys, onOpenChange: setOpenKeys })}
          onClick={({ key }) => navigate(key)}
        />
        <div className="wms-sider-footer">
          <Button
            type="text"
            block
            icon={siderCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setSiderCollapsed(!siderCollapsed)}
            style={{ color: "rgba(226,229,240,0.6)", justifyContent: siderCollapsed ? "center" : "flex-start" }}
          >
            {!siderCollapsed && "Collapse"}
          </Button>
        </div>
      </Sider>

      <Layout>
        <Header className="wms-header">
          <Breadcrumb
            style={{ flex: 1, minWidth: 0 }}
            items={
              meta
                ? [
                    { title: meta.group.label },
                    { title: meta.sub ? <Link to={meta.entry.key}>{meta.entry.label}</Link> : meta.entry.label },
                    ...(meta.sub ? [{ title: meta.sub }] : []),
                  ]
                : [{ title: "Home" }]
            }
          />
          <Button
            onClick={() => setJumpOpen(true)}
            icon={<SearchOutlined />}
            style={{ width: 240, justifyContent: "flex-start", color: "var(--ant-color-text-tertiary)" }}
          >
            <span style={{ flex: 1, textAlign: "left" }}>Jump to…</span>
            <kbd style={{ fontSize: 11, fontFamily: "inherit", padding: "1px 6px", borderRadius: 4, border: "1px solid var(--wms-surface-border)" }}>
              {isMac ? "⌘" : "Ctrl"} K
            </kbd>
          </Button>
          <LiveIndicator />
          <Tooltip title={mode === "dark" ? "Light mode" : "Dark mode"}>
            <Button shape="circle" type="text" icon={mode === "dark" ? <SunOutlined /> : <MoonOutlined />} onClick={toggleMode} aria-label="Toggle color mode" />
          </Tooltip>
          <Dropdown
            trigger={["click"]}
            menu={{
              items: [
                {
                  key: "who",
                  disabled: true,
                  label: (
                    <div style={{ padding: "4px 0" }}>
                      <div style={{ fontWeight: 600, color: "var(--ant-color-text)" }}>{me?.display_name}</div>
                      <div style={{ fontSize: 12 }}>@{me?.username}</div>
                    </div>
                  ),
                },
                { type: "divider" },
                { key: "logout", icon: <LogoutOutlined />, label: "Log out", danger: true, onClick: doLogout },
              ],
            }}
          >
            <button
              type="button"
              style={{ display: "flex", alignItems: "center", gap: 10, background: "none", border: "none", cursor: "pointer", padding: "4px 6px", borderRadius: 10, color: "inherit", font: "inherit" }}
            >
              <Avatar size={34} style={{ background: "var(--wms-grad)", fontWeight: 600, fontSize: 13 }}>
                {initials(me?.display_name)}
              </Avatar>
              {me && (
                <span style={{ textAlign: "left", lineHeight: 1.2 }}>
                  <Typography.Text strong data-testid="current-user" style={{ display: "block" }}>
                    {me.display_name}
                  </Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    @{me.username}
                  </Typography.Text>
                </span>
              )}
            </button>
          </Dropdown>
        </Header>

        <Content className="wms-content" key={pathname}>
          {meta && !meta.sub && <PageHeader title={meta.entry.label} description={meta.entry.description} />}
          {meta?.sub && (
            <Button
              type="link"
              icon={<ArrowLeftOutlined />}
              onClick={() => navigate(meta.entry.key)}
              style={{ padding: 0, marginBottom: 12, height: "auto", color: "var(--ant-color-text-secondary)" }}
            >
              {meta.entry.label}
            </Button>
          )}
          <Suspense fallback={<div style={{ display: "grid", placeItems: "center", padding: 80 }}><Spin size="large" /></div>}>
            <Outlet />
          </Suspense>
        </Content>
      </Layout>

      <QuickJump open={jumpOpen} onClose={() => setJumpOpen(false)} menu={menu} />
    </Layout>
  );
}
