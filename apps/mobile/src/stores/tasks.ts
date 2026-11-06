import * as Haptics from "expo-haptics";
import { create } from "zustand";

import { request } from "@/lib/api";
import type { DocumentSummary } from "@/lib/types";

/**
 * New-work alerts: while the app is open and signed in, open pick lists and running cycle counts are checked every
 * TASK_CHECK_MS; ones that appeared since the last check vibrate the PDA and show on the home screen until the
 * operator opens that screen.
 *
 * Polling, not push notifications: system push goes through Google's servers (FCM), which on-prem warehouse networks
 * usually cannot reach; and nothing is assigned to one person, so every operator who can do the work sees it.
 */
export type TaskKind = "pick" | "count";

const SOURCES: Record<TaskKind, string> = {
  pick: "/picks?status=OPEN&limit=200",
  count: "/cycle-counts?status=COUNTING&limit=200",
};

export const TASK_CHECK_MS = 20000;

interface TaskState {
  /** Ids seen at the last check; null until the first check, which only records what already exists */
  known: Record<TaskKind, string[] | null>;
  /** New since the operator last opened that screen */
  fresh: Record<TaskKind, number>;
  check: () => Promise<void>;
  seen: (kind: TaskKind) => void;
  reset: () => void;
}

const EMPTY = { known: { pick: null, count: null }, fresh: { pick: 0, count: 0 } };

// One check at a time: the timer and the app returning to the foreground can overlap, and an older response arriving
// last would put a stale "known" list back, so work the operator already saw would be announced again
let running: Promise<void> | null = null;

export const useTasks = create<TaskState>()((set, get) => ({
  ...EMPTY,

  check: () => {
    running ??= runCheck().finally(() => {
      running = null;
    });
    return running;
  },

  seen: (kind) => set({ fresh: { ...get().fresh, [kind]: 0 } }),

  reset: () => set(EMPTY),
}));

async function runCheck(): Promise<void> {
  const { getState: get, setState: set } = useTasks;
  let arrived = 0;
  for (const kind of Object.keys(SOURCES) as TaskKind[]) {
    let ids: string[];
    try {
      ids = (await request<DocumentSummary[]>("GET", SOURCES[kind])).map((d) => d.id);
    } catch {
      continue; // offline, or no permission for this kind of work: nothing to announce
    }
    const known = get().known[kind];
    const added = known ? ids.filter((id) => !known.includes(id)).length : 0;
    arrived += added;
    set({
      known: { ...get().known, [kind]: ids },
      fresh: { ...get().fresh, [kind]: get().fresh[kind] + added },
    });
  }
  if (arrived) {
    // Not available everywhere (some browsers, devices without a vibration motor): the on-screen notice remains
    await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning).catch(() => undefined);
  }
}
