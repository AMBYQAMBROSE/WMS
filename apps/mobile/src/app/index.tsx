import { useState } from "react";

import { MaterialCommunityIcons } from "@expo/vector-icons";
import { Redirect, useRouter, type Href } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Banner, Button, Card, Divider, EachScanToggle, IconButton, Segmented, Stat, type IconName, type Notice } from "@/components/ui";
import { errorText } from "@/lib/api";
import { useMasterData } from "@/stores/masterData";
import { useQueue } from "@/stores/queue";
import { useSession } from "@/stores/session";
import { useSettings, type ThemePreference } from "@/stores/settings";
import { useTasks } from "@/stores/tasks";
import { radius, space, type, useStyles, useTheme, type Palette } from "@/theme";

const THEMES: { value: ThemePreference; label: string; icon: IconName }[] = [
  { value: "system", label: "System", icon: "theme-light-dark" },
  { value: "light", label: "Light", icon: "white-balance-sunny" },
  { value: "dark", label: "Dark", icon: "weather-night" },
];

export default function HomeScreen() {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const router = useRouter();
  const token = useSession((st) => st.token);
  const username = useSession((st) => st.username);
  const serverUrl = useSession((st) => st.serverUrl);
  const logout = useSession((st) => st.logout);
  const data = useMasterData((st) => st.data);
  const needsLogin = useQueue((st) => st.needsLogin);
  const pending = useQueue((st) => st.ops.length);
  const failed = useQueue((st) => st.ops.filter((o) => o.status === "failed").length);
  const fresh = useTasks((st) => st.fresh);
  const theme = useSettings((st) => st.theme);
  const setTheme = useSettings((st) => st.setTheme);
  const [refreshing, setRefreshing] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  if (!token) return <Redirect href="/login" />;

  const refresh = async () => {
    setRefreshing(true);
    try {
      await useMasterData.getState().refresh();
      setNotice({ kind: "success", text: "Master data updated" });
    } catch (error) {
      setNotice({ kind: "error", text: `Update failed: ${errorText(error)}` });
    } finally {
      setRefreshing(false);
    }
  };

  const doLogout = () => {
    logout();
    router.replace("/login");
  };

  const host = serverUrl.replace(/^https?:\/\//, "").replace(/\/api\/v1\/?$/, "");
  const newWork = [
    fresh.pick && `${fresh.pick} pick list${fresh.pick > 1 ? "s" : ""}`,
    fresh.count && `${fresh.count} cycle count${fresh.count > 1 ? "s" : ""}`,
  ].filter(Boolean);

  const tiles: { key: string; title: string; hint: string; icon: IconName; href: Href; badge?: number; testID: string }[] = [
    { key: "receive", title: "Receive", hint: "Against a PO", icon: "truck-delivery-outline", href: "/receive", testID: "menu-receive" },
    { key: "putaway", title: "Put away", hint: "Dock to bin", icon: "tray-arrow-down", href: "/putaway", testID: "menu-putaway" },
    { key: "move", title: "Move", hint: "Bin to bin", icon: "swap-horizontal", href: "/move", testID: "menu-move" },
    { key: "count", title: "Count", hint: "Cycle counts", icon: "clipboard-check-outline", href: "/count", badge: fresh.count, testID: "menu-count" },
    { key: "pick", title: "Pick", hint: "Guided picking", icon: "cart-outline", href: "/pick", badge: fresh.pick, testID: "menu-pick" },
  ];

  return (
    <ScrollView style={{ backgroundColor: c.bg }} contentContainerStyle={s.screen}>
      <View style={s.hello}>
        <View style={s.avatar}>
          <Text style={s.avatarText}>{(username ?? "?").slice(0, 1).toUpperCase()}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.helloName} numberOfLines={1}>
            {username}
          </Text>
          <Text style={s.helloHost} numberOfLines={1}>
            {host}
          </Text>
        </View>
      </View>

      {needsLogin && (
        <Banner
          notice={{ kind: "warning", text: `Session expired; ${pending} record(s) waiting to submit. Sign in again to continue automatically` }}
          action={{ title: "Sign in", onPress: doLogout }}
        />
      )}
      {!data && (
        <Banner
          notice={{ kind: "warning", text: "No master data yet, so barcodes cannot be recognized. Update master data first" }}
          action={{ title: "Update now", onPress: () => void refresh(), loading: refreshing }}
        />
      )}
      <Banner notice={notice} />
      {newWork.length > 0 && <Banner notice={{ kind: "info", text: `New work: ${newWork.join(", ")}` }} />}

      <View style={s.grid}>
        {tiles.map((t) => (
          <Pressable
            key={t.key}
            testID={t.testID}
            accessibilityRole="button"
            accessibilityLabel={t.title}
            onPress={() => router.push(t.href)}
            disabled={!data}
            style={({ pressed }) => [s.tile, pressed && s.tilePressed, !data && s.tileDisabled]}
          >
            <View style={s.tileTop}>
              <View style={s.tileIcon}>
                <MaterialCommunityIcons name={t.icon} size={28} color={c.primaryText} />
              </View>
              {!!t.badge && (
                <View style={s.badge}>
                  <Text style={s.badgeText}>{`${t.badge} new`}</Text>
                </View>
              )}
            </View>
            <Text style={s.tileTitle}>{t.title}</Text>
            <Text style={s.tileHint}>{t.hint}</Text>
          </Pressable>
        ))}
        <Pressable
          testID="menu-queue"
          accessibilityRole="button"
          onPress={() => router.push("/queue")}
          style={({ pressed }) => [s.tile, pressed && s.tilePressed]}
        >
          <View style={s.tileTop}>
            <View style={[s.tileIcon, failed > 0 && { backgroundColor: c.dangerTint }]}>
              <MaterialCommunityIcons name="cloud-upload-outline" size={28} color={failed > 0 ? c.dangerText : c.primaryText} />
            </View>
            {pending > 0 && (
              <View style={[s.badge, { backgroundColor: failed > 0 ? c.danger : c.warning }]}>
                <Text style={s.badgeText}>{pending}</Text>
              </View>
            )}
          </View>
          <Text style={s.tileTitle}>Queue</Text>
          <Text style={s.tileHint}>{failed > 0 ? `${failed} failed` : pending > 0 ? `${pending} waiting` : "All sent"}</Text>
        </Pressable>
      </View>

      <Card
        title="Master data"
        icon="database-outline"
        right={<IconButton icon="refresh" label="Update master data" onPress={() => void refresh()} loading={refreshing} testID="refresh-master" />}
      >
        {data ? (
          <View style={{ flexDirection: "row", gap: space.md }}>
            <Stat label="Items" value={data.items.length.toLocaleString()} />
            <Stat label="Locations" value={data.locations.length.toLocaleString()} />
          </View>
        ) : (
          <Text style={s.muted}>Not downloaded</Text>
        )}
        {data && <Text style={s.muted}>Updated {new Date(data.generated_at + "Z").toLocaleString()}</Text>}
      </Card>

      <Card title="Settings" icon="cog-outline">
        <Segmented options={THEMES} value={theme} onChange={setTheme} />
        {/* Home stays mounted under the scan screens, so it must not repeat their testID "each-scan" */}
        <EachScanToggle testID="home-each-scan" />
        <Divider />
        <Button title={needsLogin ? "Sign in again" : "Sign out"} variant="danger" icon="logout" onPress={doLogout} />
      </Card>
    </ScrollView>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    screen: { padding: space.lg, gap: space.md, flexGrow: 1 },
    hello: { flexDirection: "row", alignItems: "center", gap: space.md, paddingVertical: space.xs },
    avatar: {
      width: 48,
      height: 48,
      borderRadius: 24,
      backgroundColor: c.primary,
      alignItems: "center",
      justifyContent: "center",
    },
    avatarText: { color: c.onPrimary, fontSize: 20, fontWeight: "700" },
    helloName: { ...type.title, color: c.text },
    helloHost: { fontSize: 13, color: c.textMuted },
    grid: { flexDirection: "row", flexWrap: "wrap", gap: space.md },
    tile: {
      flexBasis: "47%",
      flexGrow: 1,
      minHeight: 128,
      padding: space.lg,
      gap: 2,
      backgroundColor: c.surface,
      borderRadius: radius.lg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.border,
    },
    tilePressed: { backgroundColor: c.primaryTint, borderColor: c.primary },
    tileDisabled: { opacity: 0.45 },
    tileTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", marginBottom: space.sm },
    tileIcon: {
      width: 48,
      height: 48,
      borderRadius: radius.md,
      backgroundColor: c.primaryTint,
      alignItems: "center",
      justifyContent: "center",
    },
    tileTitle: { fontSize: 18, fontWeight: "700", color: c.text },
    tileHint: { fontSize: 13, color: c.textMuted },
    badge: {
      minWidth: 24,
      paddingHorizontal: 8,
      height: 24,
      borderRadius: 12,
      backgroundColor: c.primary,
      alignItems: "center",
      justifyContent: "center",
    },
    badgeText: { color: "#ffffff", fontSize: 12, fontWeight: "700", fontVariant: ["tabular-nums"] },
    muted: { fontSize: 13, color: c.textMuted },
  });
