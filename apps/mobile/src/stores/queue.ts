import * as Crypto from "expo-crypto";
import { create } from "zustand";
import { persist } from "zustand/middleware";

import { ApiError, errorText, request } from "@/lib/api";
import { zustandStorage } from "@/lib/storage";
import type { Document } from "@/lib/types";
import { useSession } from "@/stores/session";

/**
 * receive/putaway/move: create + post the document (request IDs prevent duplicates)
 * count / pick_confirm: record counted / picked quantities ("set" semantics, safe to resubmit)
 * pick_post: post the pick list (an "already posted" response on resend counts as success)
 */
export type OpType = "receive" | "putaway" | "move" | "count" | "pick_confirm" | "pick_post";

type DocumentOp = "receive" | "putaway" | "move";

export interface QueuedOp {
  id: string;
  type: OpType;
  title: string;
  payload: Record<string, unknown>;
  createdAt: string;
  createdBy: string | null;
  status: "pending" | "failed";
  error?: string;
}

export interface CompletedOp {
  id: string;
  title: string;
  docNo: string;
  completedAt: string;
}

export type SubmitOutcome =
  | { status: "done"; docNo: string }
  | { status: "queued"; reason: string }
  | { status: "failed"; error: string };

interface QueueState {
  ops: QueuedOp[];
  completed: CompletedOp[];
  syncing: boolean;
  online: boolean | null;
  needsLogin: boolean;
  lastError: string | null;
  submit: (type: OpType, title: string, payload: Record<string, unknown>) => Promise<SubmitOutcome>;
  sync: () => Promise<void>;
  remove: (id: string) => void;
}

const DOCUMENT_PATHS: Record<DocumentOp, string> = {
  receive: "/grns",
  putaway: "/putaways",
  move: "/moves",
};
const MAX_COMPLETED = 30;

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function createIdempotent(path: string, payload: Record<string, unknown>): Promise<Document> {
  try {
    return await request<Document>("POST", path, payload);
  } catch (error) {
    // Another submit with the same request ID is still being processed on the server (unique index conflict); submitting again shortly returns the created document
    if (error instanceof ApiError && error.status === 409) {
      await pause(800);
      return request<Document>("POST", path, payload);
    }
    throw error;
  }
}

async function postPick(pickId: string): Promise<string> {
  try {
    return (await request<Document>("POST", `/picks/${pickId}/post`)).doc_no;
  } catch (error) {
    // The previous post actually succeeded but the response was lost: status POSTED counts as success
    if (error instanceof ApiError && error.status === 409) {
      const pick = await request<Document>("GET", `/picks/${pickId}`);
      if (pick.status === "POSTED") return pick.doc_no;
    }
    throw error;
  }
}

async function process(op: QueuedOp): Promise<string> {
  if (op.type === "count") {
    const { count_id, entry } = op.payload as { count_id: string; entry: Record<string, unknown> };
    const doc = await request<Document>("POST", `/cycle-counts/${count_id}/counts`, entry);
    return doc.doc_no;
  }
  if (op.type === "pick_confirm") {
    const { pick_id, line_id, qty } = op.payload as { pick_id: string; line_id: string; qty: number };
    const doc = await request<Document>("POST", `/picks/${pick_id}/lines/${line_id}/confirm`, { qty });
    return doc.doc_no;
  }
  if (op.type === "pick_post") {
    return postPick((op.payload as { pick_id: string }).pick_id);
  }
  const path = DOCUMENT_PATHS[op.type];
  // Request ID = queue item id, so resending never creates a duplicate document
  const doc = await createIdempotent(path, { ...op.payload, client_request_id: op.id });
  if (doc.status === "POSTED") return doc.doc_no;
  if (doc.status !== "DRAFT") throw new ApiError("business", `Document ${doc.doc_no} has been cancelled`);
  try {
    const posted = await request<Document>("POST", `${path}/${doc.id}/post`);
    return posted.doc_no;
  } catch (error) {
    if (error instanceof ApiError && error.kind === "business") {
      // Posting rejected (e.g. over-receipt, insufficient stock): cancel the draft just created so orphan drafts do not pile up
      await request("POST", `${path}/${doc.id}/cancel`).catch(() => undefined);
    }
    throw error;
  }
}

let running: Promise<void> | null = null;

export const useQueue = create<QueueState>()(
  persist(
    (set, get) => {
      const update = (id: string, patch: Partial<QueuedOp>) =>
        set({ ops: get().ops.map((op) => (op.id === id ? { ...op, ...patch } : op)) });

      const runSync = async () => {
        if (!useSession.getState().token) return;
        set({ syncing: true });
        try {
          // Re-read the queue every round so submits added during a sync are processed too; strictly in order, never skip a failed one
          for (;;) {
            const op = get().ops.find((o) => o.status === "pending");
            if (!op) break;
            try {
              const docNo = await process(op);
              set({
                ops: get().ops.filter((o) => o.id !== op.id),
                completed: [
                  { id: op.id, title: op.title, docNo, completedAt: new Date().toISOString() },
                  ...get().completed,
                ].slice(0, MAX_COMPLETED),
                online: true,
                lastError: null,
              });
            } catch (error) {
              const kind = error instanceof ApiError ? error.kind : "network";
              if (kind === "business") {
                update(op.id, { status: "failed", error: errorText(error) });
                set({ online: true });
                continue;
              }
              set({
                online: kind === "network" ? false : true,
                needsLogin: kind === "auth",
                lastError: errorText(error),
              });
              break;
            }
          }
        } finally {
          set({ syncing: false });
        }
      };

      return {
        ops: [],
        completed: [],
        syncing: false,
        online: null,
        needsLogin: false,
        lastError: null,

        sync: () => {
          if (!running) {
            running = runSync().finally(() => {
              running = null;
            });
          }
          return running;
        },

        submit: async (type, title, payload) => {
          const id = Crypto.randomUUID();
          const op: QueuedOp = {
            id,
            type,
            title,
            payload,
            createdAt: new Date().toISOString(),
            createdBy: useSession.getState().username,
            status: "pending",
          };
          set({ ops: [...get().ops, op] });
          // If a sync round is already running it may finish before the new submit was added, so wait for it and run one more round;
          // but if the last round stopped because of being offline or an expired session, running again right away is pointless
          await get().sync();
          const stillPending = get().ops.some((o) => o.id === id && o.status === "pending");
          if (stillPending && get().online !== false && !get().needsLogin) await get().sync();

          const done = get().completed.find((c) => c.id === id);
          if (done) return { status: "done", docNo: done.docNo };
          const current = get().ops.find((o) => o.id === id);
          if (current?.status === "failed") {
            // Rejected on the spot by business rules: remove from the queue so the operator can fix it on the current screen and resubmit
            set({ ops: get().ops.filter((o) => o.id !== id) });
            return { status: "failed", error: current.error ?? "Submit failed" };
          }
          return { status: "queued", reason: get().lastError ?? "Earlier records are still waiting to submit" };
        },

        remove: (id) => set({ ops: get().ops.filter((o) => o.id !== id) }),
      };
    },
    {
      name: "wms.queue",
      storage: zustandStorage,
      partialize: (s) => ({ ops: s.ops, completed: s.completed }),
    },
  ),
);
