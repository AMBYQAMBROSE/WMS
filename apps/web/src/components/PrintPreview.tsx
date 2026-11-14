import { useEffect, useRef, useState } from "react";

import { ExportOutlined, PrinterOutlined } from "@ant-design/icons";
import { Button, Checkbox, Modal, Tabs } from "antd";

import { usePrintStore } from "@/stores/printStore";
import { useUiStore } from "@/stores/uiStore";

/**
 * The print preview: PDFs fetched by api/print, shown inside the page with Print as the focused button, so a document
 * that opens here after posting is on paper with one click (or Enter). Several PDFs (a receipt and its putaway sheet)
 * get a tab each; Print sends the one in view. Mounted once, in the main layout.
 */
export default function PrintPreview() {
  const jobs = usePrintStore((s) => s.jobs);
  const close = usePrintStore((s) => s.close);
  const autoOpen = useUiStore((s) => s.printAfterPosting);
  const setAutoOpen = useUiStore((s) => s.setPrintAfterPosting);
  const [activeKey, setActiveKey] = useState<string>();
  const frames = useRef(new Map<string, HTMLIFrameElement>());
  const printButton = useRef<HTMLButtonElement>(null);

  useEffect(() => setActiveKey(jobs[0]?.key), [jobs]);

  const active = jobs.find((j) => j.key === activeKey) ?? jobs[0];

  const openInTab = () => {
    if (active) window.open(active.url, "_blank");
  };

  const print = () => {
    if (!active) return;
    const frame = frames.current.get(active.key);
    try {
      if (!frame?.contentWindow) throw new Error("No preview");
      frame.contentWindow.focus();
      frame.contentWindow.print();
    } catch {
      // A browser that cannot print the embedded PDF: its own PDF viewer in a new tab can
      openInTab();
    }
  };

  const frame = (job: (typeof jobs)[number]) => (
    <iframe
      key={job.key}
      ref={(el) => {
        if (el) frames.current.set(job.key, el);
        else frames.current.delete(job.key);
      }}
      src={job.url}
      title={job.title}
      className="wms-print-frame"
      data-testid="print-preview-frame"
    />
  );

  return (
    <Modal
      open={jobs.length > 0}
      title={jobs.length === 1 ? `Print ${active?.title ?? ""}` : "Print"}
      width="min(1100px, calc(100vw - 32px))"
      centered
      destroyOnHidden
      onCancel={close}
      // Opened over another dialog (label options), that dialog would keep the focus: Enter must print here
      afterOpenChange={(open) => open && printButton.current?.focus()}
      data-testid="print-preview"
      footer={
        <div className="wms-print-footer">
          <Checkbox checked={autoOpen} onChange={(e) => setAutoOpen(e.target.checked)} data-testid="print-after-posting">
            Open this after posting a document
          </Checkbox>
          <span style={{ flex: 1 }} />
          <Button icon={<ExportOutlined />} onClick={openInTab}>
            Open in new tab
          </Button>
          <Button onClick={close}>Close</Button>
          <Button ref={printButton} type="primary" icon={<PrinterOutlined />} autoFocus onClick={print} data-testid="print-preview-print">
            Print{jobs.length > 1 && active ? ` ${active.title}` : ""}
          </Button>
        </div>
      }
    >
      {jobs.length > 1 ? (
        <Tabs
          activeKey={active?.key}
          onChange={setActiveKey}
          // Every PDF stays loaded, so switching tabs is instant and each can be printed in turn
          items={jobs.map((j) => ({ key: j.key, label: j.title, children: frame(j), forceRender: true }))}
        />
      ) : (
        active && frame(active)
      )}
    </Modal>
  );
}
