import { useState } from "react";

import { PrinterOutlined } from "@ant-design/icons";
import { Button } from "antd";

// No imports from ui/documents: DocTitle in ui.tsx renders PrintButton, and that would make an import cycle
import { printDocument } from "@/api/print";

/** Opens the document's printable report (PDF) in the print preview */
export function PrintButton({ documentId, docNo }: { documentId: string; docNo?: string }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      type="text"
      size="small"
      icon={<PrinterOutlined />}
      loading={busy}
      data-testid="print-document"
      onClick={async () => {
        setBusy(true);
        await printDocument(documentId, docNo);
        setBusy(false);
      }}
    >
      Print
    </Button>
  );
}
