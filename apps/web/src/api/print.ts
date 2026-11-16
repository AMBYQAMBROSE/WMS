import { isAxiosError } from "axios";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import { usePrintStore, type PrintJob } from "@/stores/printStore";

/** A PDF to fetch: GET `path` (document reports), or POST `body` to it (labels) */
export interface PdfRequest {
  path: string;
  body?: unknown;
  /** Shown above the preview, and on its tab when several PDFs open together */
  title: string;
}

async function fetchPdf(request: PdfRequest, index: number): Promise<PrintJob> {
  const res =
    request.body === undefined
      ? await apiClient.get<Blob>(request.path, { responseType: "blob" })
      : await apiClient.post<Blob>(request.path, request.body, { responseType: "blob" });
  return { key: `${index}:${request.path}`, title: request.title, url: URL.createObjectURL(res.data) };
}

/**
 * Fetch PDFs from the server and show them in the print preview, where one click on Print sends the one in view to
 * the printer (browser print dialog, the printer's own settings: paper size, scaling "Actual size").
 *
 * The preview is part of the page, not a new tab, so it can open by itself after an operation: a tab opened without
 * a click would be blocked as a pop-up. Returns false when nothing could be shown.
 *
 * `quiet`: for previews nobody asked for (opened after posting). PDFs that fail are left out without an error message.
 */
export async function openPdfs(requests: PdfRequest[], { quiet = false } = {}): Promise<boolean> {
  const results = await Promise.allSettled(requests.map(fetchPdf));
  const jobs = results.flatMap((r) => (r.status === "fulfilled" ? [r.value] : []));
  const failed = results.find((r) => r.status === "rejected");
  if (failed && !quiet) showError(await readBlobError(failed.reason));
  if (!jobs.length) return false;
  usePrintStore.getState().show(jobs);
  return true;
}

export const openPdf = (path: string, body?: unknown, title = "Print preview") => openPdfs([{ path, body, title }]);

/** With responseType "blob" an error body arrives as a Blob too; turn it back into JSON so the server's message shows */
async function readBlobError(error: unknown): Promise<unknown> {
  if (isAxiosError(error) && error.response?.data instanceof Blob) {
    try {
      error.response.data = JSON.parse(await error.response.data.text());
    } catch {
      // Not JSON: keep the generic message
    }
  }
  return error;
}

export interface Printable {
  id: string;
  doc_no: string;
}

/**
 * The printed reports of documents (A4: details, lines, signature boxes, document number as a barcode), one tab each.
 * Fetching a report records a print in the document's history.
 */
export const printDocuments = (docs: Printable[], options?: { quiet?: boolean }) =>
  openPdfs(docs.map((d) => ({ path: `/documents/${d.id}/print`, title: d.doc_no })), options);

export const printDocument = (documentId: string, docNo = "Print preview") => printDocuments([{ id: documentId, doc_no: docNo }]);
