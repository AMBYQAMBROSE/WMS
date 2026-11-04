import type { ReactNode } from "react";

import { InfoCircleOutlined, SearchOutlined } from "@ant-design/icons";
import { Input, Typography } from "antd";

import { Toolbar } from "@/components/ui";

/** Search box above master data lists: with large data the list only loads the first LIMIT rows, so search is how you find the rest */
export const MASTER_LIST_LIMIT = 500;

export default function MasterSearch({
  placeholder,
  onSearch,
  shown,
  actions,
}: {
  placeholder: string;
  onSearch: (keyword: string) => void;
  shown?: number;
  /** Buttons on the right of the toolbar (e.g. "New item") */
  actions?: ReactNode;
}) {
  return (
    <Toolbar
      left={
        <>
          <Input.Search
            allowClear
            prefix={<SearchOutlined style={{ color: "var(--ant-color-text-quaternary)" }} />}
            placeholder={placeholder}
            style={{ width: 320 }}
            onSearch={(v) => onSearch(v.trim())}
          />
          {shown === MASTER_LIST_LIMIT && (
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              <InfoCircleOutlined /> Showing the latest {MASTER_LIST_LIMIT} only; use search to find others
            </Typography.Text>
          )}
        </>
      }
      right={actions}
    />
  );
}
