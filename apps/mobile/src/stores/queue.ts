import * as Crypto from "expo-crypto";
import { create } from "zustand";
import { persist } from "zustand/middleware";

import { ApiError, errorText, request } from "@/lib/api";
import { loadPhoto, removePhoto, type PhotoRef } from "@/lib/photos";
import { zustandStorage } from "@/lib/storage";
import type { Document } from "@/lib/types";
import { useSession } from "@/stores/session";

/**
 * receive/putaway/move: create + post the document (request IDs prevent duplicates)
 * count / pick_confirm: record counted / picked quantities ("set" semantics, safe to resubmit)
 * pick_post: post the pick list (an "already posted" response on resend counts as success)
 * putaway_put: put part or all of a putaway sheet line into a bin (sent with an Idempotency-Key: a resend after a lost
 *   response is answered from the first put instead of putting the quantity twice)
 * putaway_post: post the putaway sheet once every line is put away (same "already posted" rule as pick_post)
 * attach: photos for a document that already exists (payload.document_id), e.g. what a count found
 * Any operation may carry photos: they are uploaded to its document once that exists.
 */
export type OpType = "receive" | "putaway" | "move" | "count" | "pick_confirm" | "pick_post" | "putaway_put" | "putaway_post" | "attach";

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
  /** What the operation contains, for people (item, quantity, locations): the payload only holds ids */
  details?: string[];
  /** Images are in file storage (lib/photos.ts); removed from there once uploaded */
  photos?: PhotoRef[];
}

export interface CompletedOp {
  id: string;
  title: string;
  docNo: string;
  completedAt: string;
  /** E.g. a photo the server refused: the work itself was saved */
  warning?: string;
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
  submit: (
    type: OpType,
    title: string,
    payload: Record<string, unknown>,
    details?: string[],
    photos?: PhotoRef[],
  ) => Promise<SubmitOutcome>;
  sync: () => Promise<void>;
  /** Submit a failed operation again, e.g. after the stock problem it ran into was fixed */
  retry: (id: string) => Promise<void>;
  remove: (id: string) => void;
}

/**
 * Operations are submitted only under the account that created them: whoever signs in next on a shared PDA must not
 * post the previous person's work as their own (the server records the signed-in user as the one who did it).
 * Operations from before this rule (no creator) count as the current user's.
 */
export const isMine = (op: QueuedOp, username: string | null) => !op.createdBy || op.createdBy === username;

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

/** Post a document worked line by line (pick list, putaway sheet) */
async function postWorked(path: string, docId: string): Promise<string> {
  try {
    return (await request<Document>("POST", `${path}/${docId}/post`)).doc_no;
  } catch (error) {
    // The previous post actually succeeded but the response was lost: status POSTED counts as success
    if (error instanceof ApiError && error.status === 409) {
      const doc = await request<Document>("GET", `${path}/${docId}`);
      if (doc.status === "POSTED") return doc.doc_no;
    }
    throw error;
  }
}

interface Processed {
  docNo: string;
  docId: string;
}

/**
 * Each photo is sent with its own Idempotency-Key, so repeating this after a lost response or an interruption never
 * stores a photo twice. A photo the server refuses (no permission, not an image) is dropped with a warning: the work it
 * belongs to was saved, and marking that as failed would be wrong.
 */
async function uploadPhotos(docId: string, photos: PhotoRef[] = []): Promise<string | undefined> {
  const refused: string[] = [];
  for (const photo of photos) {
    const content = await loadPhoto(photo.id);
    if (content) {
      try {
        await request("POST", `/documents/${docId}/attachments`, { content_base64: content, caption: photo.caption }, {
          headers: { "Idempotency-Key": `photo-${photo.id}` },
        });
      } catch (error) {
        if (!(error instanceof ApiError && error.kind === "business")) throw error; // offline etc.: try again later
        refused.push(errorText(error));
      }
    }
    await removePhoto(photo.id);
  }
  return refused.length ? `${refused.length} photo(s) not saved: ${refused[0]}` : undefined;
}

async function process(op: QueuedOp): Promise<Processed> {
  if (op.type === "attach") {
    const { document_id, doc_no } = op.payload as { document_id: string; doc_no: string };
    return { docNo: doc_no, docId: document_id };
  }
  if (op.type === "count") {
    const { count_id, entry } = op.payload as { count_id: string; entry: Record<string, unknown> };
    const doc = await request<Document>("POST", `/cycle-counts/${count_id}/counts`, entry);
    return { docNo: doc.doc_no, docId: doc.id };
  }
  if (op.type === "pick_confirm") {
    const { pick_id, line_id, qty } = op.payload as { pick_id: string; line_id: string; qty: number };
    const doc = await request<Document>("POST", `/picks/${pick_id}/lines/${line_id}/confirm`, { qty });
    return { docNo: doc.doc_no, docId: doc.id };
  }
  if (op.type === "pick_post") {
    const pickId = (op.payload as { pick_id: string }).pick_id;
    return { docNo: await postWorked("/picks", pickId), docId: pickId };
  }
  if (op.type === "putaway_put") {
    const { sheet_id, line_id, to_location_id, qty } = op.payload as { sheet_id: string; line_id: string; to_location_id: string; qty: number };
    const doc = await request<Document>("POST", `/putaways/${sheet_id}/lines/${line_id}/put`, { to_location_id, qty }, {
      headers: { "Idempotency-Key": `put-${op.id}` },
    });
    return { docNo: doc.doc_no, docId: doc.id };
  }
  if (op.type === "putaway_post") {
    const sheetId = (op.payload as { sheet_id: string }).sheet_id;
    return { docNo: await postWorked("/putaways", sheetId), docId: sheetId };
  }
  const path = DOCUMENT_PATHS[op.type];
  // Request ID = queue item id, so resending never creates a duplicate document
  const doc = await createIdempotent(path, { ...op.payload, client_request_id: op.id });
  if (doc.status === "POSTED") return { docNo: doc.doc_no, docId: doc.id };
  if (doc.status !== "DRAFT") throw new ApiError("business", `Document ${doc.doc_no} has been cancelled`);
  try {
    const posted = await request<Document>("POST", `${path}/${doc.id}/post`);
    return { docNo: posted.doc_no, docId: posted.id };
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
            const me = useSession.getState().username;
            const op = get().ops.find((o) => o.status === "pending" && isMine(o, me));
            if (!op) break;
            try {
              const { docNo, docId } = await process(op);
              const warning = await uploadPhotos(docId, op.photos);
              set({
                ops: get().ops.filter((o) => o.id !== op.id),
                completed: [
                  { id: op.id, title: op.title, docNo, completedAt: new Date().toISOString(), warning },
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

        submit: async (type, title, payload, details, photos) => {
          const id = Crypto.randomUUID();
          const op: QueuedOp = {
            id,
            type,
            title,
            payload,
            createdAt: new Date().toISOString(),
            createdBy: useSession.getState().username,
            status: "pending",
            details,
            photos,
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

        retry: async (id) => {
          const op = get().ops.find((o) => o.id === id);
          if (!op || op.status !== "failed") return;
          // A new id is a new request id: the failed attempt's draft was cancelled on the server, and resending its id
          // would only find that cancelled draft again. Moved to the end, behind whatever was queued since.
          const again: QueuedOp = { ...op, id: Crypto.randomUUID(), status: "pending", error: undefined };
          set({ ops: [...get().ops.filter((o) => o.id !== id), again] });
          await get().sync();
        },

        remove: (id) => {
          const op = get().ops.find((o) => o.id === id);
          for (const photo of op?.photos ?? []) void removePhoto(photo.id);
          set({ ops: get().ops.filter((o) => o.id !== id) });
        },
      };
    },
    {
      name: "wms.queue",
      storage: zustandStorage,
      partialize: (s) => ({ ops: s.ops, completed: s.completed }),
    },
  ),
);
