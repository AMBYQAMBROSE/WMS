import { create } from "zustand";

/** One PDF ready to print: `url` is a blob URL owned by the store (revoked when the preview closes) */
export interface PrintJob {
  key: string;
  title: string;
  url: string;
}

interface PrintState {
  jobs: PrintJob[];
  show: (jobs: PrintJob[]) => void;
  close: () => void;
}

const revoke = (jobs: PrintJob[]) => jobs.forEach((j) => URL.revokeObjectURL(j.url));

/** The PDFs shown in the print preview (see components/PrintPreview) */
export const usePrintStore = create<PrintState>()((set, get) => ({
  jobs: [],
  show: (jobs) => {
    revoke(get().jobs);
    set({ jobs });
  },
  close: () => {
    revoke(get().jobs);
    set({ jobs: [] });
  },
}));
