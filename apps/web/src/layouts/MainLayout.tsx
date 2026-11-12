import { Suspense, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  AppstoreOutlined,
  BarChartOutlined,
  CheckOutlined,
  ColumnHeightOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  DownloadOutlined,
  EnterOutlined,
  ExportOutlined,
  HomeOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuOutlined,
  MenuUnfoldOutlined,
  MoonOutlined,
  PlusOutlined,
  RollbackOutlined,
  SearchOutlined,
  SettingOutlined,
  SunOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { useQueryClient } from "@tanstack/react-query";
import { Avatar, Breadcrumb, Button, Drawer, Dropdown, Grid, Input, Layout, Menu, Modal, Skeleton, Tooltip, Typography, type InputRef, type MenuProps } from "antd";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router";

import { useCan, useFeature, useMe } from "@/api/me";
import TopLoader from "@/components/TopLoader";
import { BackLink, BrandMark, EmptyState, PageHeader } from "@/components/ui";
import { useLiveStore, useLiveUpdates, type LiveStatus } from "@/api/live";
import { useAuthStore } from "@/stores/authStore";
import { useUiStore } from "@/stores/uiStore";
import { SHELL, type ThemePreference } from "@/theme";
import { withThemeReveal } from "@/theme/motion";

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
  /** The list has a "new" page (route key + "/new"): offered as a quick action in the command palette */
  create?: { label: string; perm: string };
  /** The page renders its own header (title/description) instead of the generic one */
  ownHeader?: boolean;
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
      { key: "/dashboard", label: "Dashboard", description: "Today's activity, open work and stock health at a glance", perm: "report.read", ownHeader: true },
      { key: "/assistant", label: "AI assistant", description: "Ask about stock, documents and reports in plain language", perm: "ai.assistant", feature: "AI_ASSISTANT", ownHeader: true },
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
      { key: "/purchase-orders", label: "Purchase orders", description: "Plan what suppliers will deliver", perm: "purchase_order.read", create: { label: "New purchase order", perm: "purchase_order.create" } },
      { key: "/grns", label: "Goods receipts", description: "Record goods arriving at the dock", perm: "grn.read", create: { label: "New goods receipt", perm: "grn.create" } },
      { key: "/putaways", label: "Putaways", description: "Move received goods into storage bins", perm: "putaway.read", create: { label: "New putaway", perm: "putaway.create" } },
    ],
  },
  {
    key: "outbound",
    label: "Outbound",
    icon: <ExportOutlined />,
    children: [
      { key: "/cart", label: "Shopping cart", description: "Browse items and place an order in a few clicks", perm: "cart.order" },
      { key: "/sales-orders", label: "Sales orders", description: "Customer orders from allocation to shipment", perm: "sales_order.read", create: { label: "New sales order", perm: "sales_order.create" } },
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
      { key: "/moves", label: "Moves", description: "Bin-to-bin transfers", perm: "move.read", create: { label: "New move", perm: "move.create" } },
      { key: "/adjustments", label: "Stock adjustments", description: "Correct quantities with a reason", perm: "adjustment.read", create: { label: "New adjustment", perm: "adjustment.create" } },
      { key: "/cycle-counts", label: "Cycle counts", description: "Count bins and reconcile differences", perm: "cycle_count.read", create: { label: "Start cycle count", perm: "cycle_count.create" } },
      { key: "/repacks", label: "Repacks", description: "Convert items into other items or packaging", perm: "repack.read", feature: "REPACK", create: { label: "New repack", perm: "repack.create" } },
    ],
  },
  {
    key: "returns",
    label: "Returns & assets",
    icon: <RollbackOutlined />,
    children: [
      { key: "/returns-in", label: "Customer returns", description: "Goods coming back from customers", perm: "return_in.read", feature: "RETURNS", create: { label: "New customer return", perm: "return_in.create" } },
      { key: "/returns-out", label: "Returns to supplier", description: "Goods sent back to suppliers", perm: "return_out.read", feature: "RETURNS", create: { label: "New return to supplier", perm: "return_out.create" } },
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
      { key: "/label-settings", label: "Labels & printing", description: "Label sizes and layouts for item and location labels", perm: "system.settings" },
      { key: "/integration", label: "Integrations", description: "Webhook connectors and delivery history", perm: "integration.read" },
      { key: "/imports", label: "Data import", description: "Bulk-load master data, opening stock and orders from spreadsheets", perm: ["item.create", "location.create", "business_partner.create", "adjustment.post", "purchase_order.create", "sales_order.create"] },
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
  if (isLoading) return null;
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

const isTyping = (target: EventTarget | null) => {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
};

interface PaletteEntry {
  key: string;
  to: string;
  label: string;
  hint: string;
  icon: ReactNode;
  kind: "page" | "action";
}

/** Ctrl/Cmd+K: jump to any page the user can open, or start a new document */
function QuickJump({ open, onClose, menu }: { open: boolean; onClose: () => void; menu: MenuGroup[] }) {
  const navigate = useNavigate();
  const can = useCan();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<InputRef>(null);
  const list = useRef<HTMLDivElement>(null);

  const entries: PaletteEntry[] = useMemo(
    () => [
      ...menu.flatMap((g) =>
        g.children.map((c) => ({ key: c.key, to: c.key, label: c.label, hint: `${g.label} · ${c.description ?? ""}`, icon: g.icon, kind: "page" as const })),
      ),
      ...menu.flatMap((g) =>
        g.children
          .filter((c) => c.create && can(c.create.perm))
          .map((c) => ({ key: `${c.key}/new`, to: `${c.key}/new`, label: c.create!.label, hint: `${g.label} · Create`, icon: <PlusOutlined />, kind: "action" as const })),
      ),
    ],
    [menu, can],
  );
  const needle = q.trim().toLowerCase();
  const results = needle ? entries.filter((e) => `${e.label} ${e.hint}`.toLowerCase().includes(needle)) : entries;

  useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
      setTimeout(() => input.current?.focus(), 50);
    }
  }, [open]);

  // Keep the highlighted row in view while moving with the arrow keys
  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const go = (to: string) => {
    navigate(to);
    onClose();
  };

  let lastKind: PaletteEntry["kind"] | undefined;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      closable={false}
      width={600}
      styles={{ container: { padding: 0, overflow: "hidden" }, body: { padding: 0 } }}
      style={{ top: "12vh" }}
      destroyOnHidden
      afterOpenChange={(visible) => visible && input.current?.focus()}
    >
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--wms-border-subtle)" }}>
        <Input
          ref={input}
          autoFocus
          size="large"
          variant="borderless"
          prefix={<SearchOutlined style={{ color: "var(--ant-color-text-tertiary)", marginRight: 6 }} />}
          placeholder="Jump to a page…"
          aria-label="Jump to a page"
          role="combobox"
          aria-expanded
          aria-controls="wms-palette-list"
          aria-activedescendant={results[active] ? `wms-palette-${active}` : undefined}
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
              go(results[active].to);
            }
          }}
        />
      </div>
      <div ref={list} id="wms-palette-list" role="listbox" style={{ padding: 6, maxHeight: 420, overflowY: "auto" }}>
        {results.length === 0 && <EmptyState icon={<SearchOutlined />} title="No matching page" hint="Try a module name such as “receipts” or “stock”." />}
        {results.map((e, i) => {
          const heading = e.kind !== lastKind ? (e.kind === "page" ? "Pages" : "Create") : null;
          lastKind = e.kind;
          return (
            <div key={e.key}>
              {heading && (
                <div style={{ padding: "8px 10px 4px", fontSize: 11.5, fontWeight: 600, color: "var(--ant-color-text-tertiary)" }}>{heading}</div>
              )}
              <div
                id={`wms-palette-${i}`}
                data-index={i}
                role="option"
                aria-selected={i === active}
                onMouseEnter={() => setActive(i)}
                onClick={() => go(e.to)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "8px 10px",
                  borderRadius: 6,
                  cursor: "pointer",
                  background: i === active ? "var(--wms-surface-hover)" : undefined,
                }}
              >
                <span style={{ color: i === active ? "var(--ant-color-primary)" : "var(--ant-color-text-tertiary)", fontSize: 15, width: 18, display: "grid", placeItems: "center" }}>
                  {e.icon}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 13.5 }}>{e.label}</div>
                  <Typography.Text type="secondary" ellipsis style={{ fontSize: 12, display: "block" }}>
                    {e.hint}
                  </Typography.Text>
                </div>
                {i === active && <EnterOutlined style={{ color: "var(--ant-color-text-tertiary)" }} />}
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ display: "flex", gap: 16, padding: "8px 14px", borderTop: "1px solid var(--wms-border-subtle)", fontSize: 12, color: "var(--ant-color-text-tertiary)" }}>
        <span><kbd className="wms-kbd">↑</kbd> <kbd className="wms-kbd">↓</kbd> to move</span>
        <span><kbd className="wms-kbd">Enter</kbd> to open</span>
        <span><kbd className="wms-kbd">Esc</kbd> to close</span>
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
function LiveIndicator({ compact }: { compact?: boolean }) {
  const status = useLiveStore((s) => s.status);
  const text = LIVE_TEXT[status];
  return (
    <Tooltip title={text.tip}>
      <span className={`wms-live wms-live-${status}`} role="status" aria-label={`Live updates: ${text.label}`}>
        <span className="wms-live-dot" />
        {!compact && text.label}
      </span>
    </Tooltip>
  );
}

const THEME_OPTIONS: { key: ThemePreference; label: string; icon: ReactNode }[] = [
  { key: "light", label: "Light", icon: <SunOutlined /> },
  { key: "dark", label: "Dark", icon: <MoonOutlined /> },
  { key: "system", label: "System", icon: <DesktopOutlined /> },
];

function ThemeMenu() {
  const { preference, mode, setPreference } = useUiStore();
  return (
    <Dropdown
      trigger={["click"]}
      placement="bottomRight"
      menu={{
        selectable: true,
        selectedKeys: [preference],
        items: THEME_OPTIONS.map((o) => ({
          key: o.key,
          icon: o.icon,
          label: (
            <span style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24, minWidth: 110 }}>
              {o.label}
              {preference === o.key && <CheckOutlined style={{ fontSize: 12 }} />}
            </span>
          ),
          onClick: ({ domEvent }) => withThemeReveal(() => setPreference(o.key), "clientX" in domEvent ? domEvent : null),
        })),
      }}
    >
      <Tooltip title="Theme" placement="bottom">
        <Button type="text" icon={mode === "dark" ? <MoonOutlined /> : <SunOutlined />} aria-label="Toggle color mode" />
      </Tooltip>
    </Dropdown>
  );
}

/** Navigation menu: shared by the desktop sider and the mobile drawer */
function NavMenu({
  menu,
  selected,
  collapsed,
  openKeys,
  onOpenChange,
  onNavigate,
}: {
  menu: MenuGroup[];
  selected?: string;
  collapsed: boolean;
  openKeys: string[];
  onOpenChange: (keys: string[]) => void;
  onNavigate: (key: string) => void;
}) {
  const items: MenuProps["items"] = menu.map(({ key, label, icon, children }) => ({
    key,
    label,
    icon,
    children: children.map(({ key: k, label: l }) => ({ key: k, label: l })),
  }));
  return (
    <Menu
      className="wms-sider-menu"
      mode="inline"
      inlineIndent={14}
      items={items}
      selectedKeys={selected ? [selected] : []}
      {...(collapsed ? {} : { openKeys, onOpenChange })}
      onClick={({ key }) => onNavigate(key)}
    />
  );
}

export default function MainLayout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const queryClient = useQueryClient();
  const screens = Grid.useBreakpoint();
  // Before the first measurement every breakpoint is undefined: treat that as desktop to avoid a flash of the mobile layout
  const mobile = screens.lg === false;
  const narrow = screens.md === false;
  const logout = useAuthStore((state) => state.logout);
  const { siderCollapsed, setSiderCollapsed, density, setDensity, animations, setAnimations } = useUiStore();
  const { data: me } = useMe();
  const menu = useVisibleMenu();
  const meta = useRouteMeta(pathname);
  const [openKeys, setOpenKeys] = useState<string[]>(meta ? [meta.group.key] : []);
  const [jumpOpen, setJumpOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  useLiveUpdates();

  // Keep the current route's group expanded when navigating from elsewhere (quick jump, links in tables)
  useEffect(() => {
    if (meta && !openKeys.includes(meta.group.key)) setOpenKeys((keys) => [...keys, meta.group.key]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta?.group.key]);

  // The mobile drawer closes once a page is chosen
  useEffect(() => setDrawerOpen(false), [pathname]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setJumpOpen(true);
      } else if (e.key === "[" && !e.ctrlKey && !e.metaKey && !e.altKey && !isTyping(e.target)) {
        // "[" folds the sidebar, as in many productivity tools; never while typing (scanners type into inputs)
        setSiderCollapsed(!useUiStore.getState().siderCollapsed);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setSiderCollapsed]);

  const createLabel = meta?.sub === "New" ? meta.entry.create?.label : undefined;
  useEffect(() => {
    const sub = createLabel ?? (meta?.sub ? `${meta.sub} · ${meta.entry.label}` : meta?.entry.label);
    document.title = sub ? `${sub} · WMS` : "WMS";
  }, [meta, createLabel]);

  const doLogout = () => {
    logout();
    // After switching accounts the previous user's cached data must not be visible
    queryClient.clear();
  };

  const isMac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);
  const collapsed = siderCollapsed && !mobile;

  const brand = (
    <Link to="/" className="wms-brand" aria-label="WMS home">
      <BrandMark />
      {!collapsed && (
        <div>
          <div className="wms-brand-name">WMS</div>
          <div className="wms-brand-sub">Warehouse cloud</div>
        </div>
      )}
    </Link>
  );

  const nav = (
    <NavMenu
      menu={menu}
      selected={meta?.entry.key}
      collapsed={collapsed}
      openKeys={openKeys}
      onOpenChange={setOpenKeys}
      onNavigate={(key) => navigate(key)}
    />
  );

  return (
    <Layout style={{ minHeight: "100vh" }}>
      {!mobile && (
        <Sider
          className={`wms-sider${collapsed ? " wms-sider-collapsed" : ""}`}
          width={SHELL.siderWidth}
          collapsedWidth={SHELL.siderCollapsedWidth}
          collapsible
          collapsed={collapsed}
          onCollapse={setSiderCollapsed}
          trigger={null}
          aria-label="Main navigation"
        >
          {brand}
          {nav}
          <div className="wms-sider-footer">
            <Tooltip title={collapsed ? "Expand sidebar  [" : undefined} placement="right">
              <Button
                type="text"
                block
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={() => setSiderCollapsed(!siderCollapsed)}
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                style={{ justifyContent: collapsed ? "center" : "flex-start" }}
              >
                {!collapsed && (
                  <span style={{ display: "flex", flex: 1, justifyContent: "space-between", alignItems: "center" }}>
                    Collapse <kbd className="wms-kbd">[</kbd>
                  </span>
                )}
              </Button>
            </Tooltip>
          </div>
        </Sider>
      )}

      {mobile && (
        <Drawer
          className="wms-nav-drawer"
          placement="left"
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          size={SHELL.siderWidth + 24}
          closable={false}
          title={null}
        >
          {brand}
          {nav}
        </Drawer>
      )}

      <Layout>
        <TopLoader />
        <Header className="wms-header">
          {mobile && <Button type="text" icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} aria-label="Open navigation" />}
          <Breadcrumb
            items={
              meta
                ? [
                    ...(narrow ? [] : [{ title: <Link to="/" aria-label="Home"><HomeOutlined /></Link> }, { title: meta.group.label }]),
                    // Phones: the back link under the header already leads to the list, so only the current page is named
                    ...(narrow && meta.sub ? [] : [{ title: meta.sub ? <Link to={meta.entry.key}>{meta.entry.label}</Link> : meta.entry.label }]),
                    ...(meta.sub ? [{ title: createLabel ?? meta.sub }] : []),
                  ]
                : [{ title: <HomeOutlined aria-label="Home" /> }]
            }
          />
          <div className="wms-header-actions">
            {narrow ? (
              <Button type="text" icon={<SearchOutlined />} onClick={() => setJumpOpen(true)} aria-label="Jump to a page" />
            ) : (
              <Button className="wms-search-trigger" onClick={() => setJumpOpen(true)} icon={<SearchOutlined />}>
                <span style={{ flex: 1, textAlign: "left" }}>Jump to…</span>
                <span style={{ display: "inline-flex", gap: 3 }}>
                  <kbd className="wms-kbd">{isMac ? "⌘" : "Ctrl"}</kbd>
                  <kbd className="wms-kbd">K</kbd>
                </span>
              </Button>
            )}
            <LiveIndicator compact={narrow} />
            <ThemeMenu />
            <Dropdown
              trigger={["click"]}
              placement="bottomRight"
              menu={{
                items: [
                  {
                    key: "who",
                    disabled: true,
                    style: { cursor: "default" },
                    label: (
                      <div style={{ padding: "4px 0", minWidth: 200 }}>
                        <div style={{ fontWeight: 600, color: "var(--ant-color-text)" }}>{me?.display_name}</div>
                        <div style={{ fontSize: 12 }}>@{me?.username}</div>
                      </div>
                    ),
                  },
                  { type: "divider" },
                  {
                    key: "density",
                    icon: <ColumnHeightOutlined />,
                    label: "Table density",
                    children: (["comfortable", "compact"] as const).map((d) => ({
                      key: `density-${d}`,
                      label: (
                        <span style={{ display: "flex", justifyContent: "space-between", gap: 24, minWidth: 120 }}>
                          {d === "comfortable" ? "Comfortable" : "Compact"}
                          {density === d && <CheckOutlined style={{ fontSize: 12 }} />}
                        </span>
                      ),
                      onClick: () => setDensity(d),
                    })),
                  },
                  {
                    key: "animations",
                    icon: <ThunderboltOutlined />,
                    label: "Animations",
                    children: ([true, false] as const).map((on) => ({
                      key: `animations-${on ? "on" : "off"}`,
                      label: (
                        <span style={{ display: "flex", justifyContent: "space-between", gap: 24, minWidth: 120 }}>
                          {on ? "On" : "Off"}
                          {animations === on && <CheckOutlined style={{ fontSize: 12 }} />}
                        </span>
                      ),
                      onClick: () => setAnimations(on),
                    })),
                  },
                  { type: "divider" },
                  { key: "logout", icon: <LogoutOutlined />, label: "Log out", danger: true, onClick: doLogout },
                ],
              }}
            >
              <button type="button" className="wms-user-trigger" aria-label="Account menu">
                <Avatar size={28} className="wms-avatar">
                  {initials(me?.display_name)}
                </Avatar>
                {me && !narrow && (
                  <span style={{ textAlign: "left", lineHeight: 1.2 }}>
                    <Typography.Text strong data-testid="current-user" style={{ display: "block", fontSize: 13 }}>
                      {me.display_name}
                    </Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 11.5 }}>
                      @{me.username}
                    </Typography.Text>
                  </span>
                )}
              </button>
            </Dropdown>
          </div>
        </Header>

        <Content className="wms-content" key={pathname} id="main" tabIndex={-1} style={{ outline: "none" }}>
          {meta && !meta.sub && !meta.entry.ownHeader && <PageHeader title={meta.entry.label} description={meta.entry.description} />}
          {meta?.sub && <BackLink to={meta.entry.key} label={meta.entry.label} />}
          <Suspense
            fallback={
              <div style={{ display: "grid", gap: 16 }} aria-busy="true">
                <Skeleton.Input active block style={{ height: 52 }} />
                <Skeleton active paragraph={{ rows: 8 }} />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </Content>
      </Layout>

      <QuickJump open={jumpOpen} onClose={() => setJumpOpen(false)} menu={menu} />
    </Layout>
  );
}
