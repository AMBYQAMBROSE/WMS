import { isAxiosError } from "axios";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";

/**
 * Ask the server for a PDF (labels, document reports) and open it in a new tab, where it is printed with the
 * browser's print dialog and the printer's own settings (paper size, scaling "Actual size").
 *
 * The tab is opened before the request, while the click still counts as a user action; opening it after waiting for
 * the server would be blocked as a pop-up. Returns false when the PDF could not be made (the error is shown).
 * Without a body the PDF is fetched with GET (document reports), with one it is POSTed (labels).
 */
export async function openPdf(path: string, body?: unknown): Promise<boolean> {
  const tab = window.open("", "_blank");
  tab?.document.write("<title>Preparing PDF…</title><p style='font:14px sans-serif;margin:24px'>Preparing PDF…</p>");
  try {
    const res =
      body === undefined
        ? await apiClient.get<Blob>(path, { responseType: "blob" })
        : await apiClient.post<Blob>(path, body, { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    if (tab) {
      tab.location.href = url;
    } else {
      // Pop-ups blocked anyway: download instead
      const a = document.createElement("a");
      a.href = url;
      a.download = "print.pdf";
      a.click();
    }
    // The tab has loaded it long before this; keeping the URL any longer only holds memory
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
    return true;
  } catch (error) {
    tab?.close();
    showError(await readBlobError(error));
    return false;
  }
}

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

/** The printed report of a document (A4: details, lines, signature boxes, document number as a barcode) */
export const printDocument = (documentId: string) => openPdf(`/documents/${documentId}/print`);
