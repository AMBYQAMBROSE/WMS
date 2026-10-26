export const STATUS_LABELS: Record<string, { text: string; color: string }> = {
  DRAFT: { text: "草稿", color: "default" },
  CONFIRMED: { text: "已确认", color: "blue" },
  PARTIALLY_RECEIVED: { text: "部分收货", color: "orange" },
  RECEIVED: { text: "已收货", color: "green" },
  CLOSED: { text: "已结案", color: "purple" },
  CANCELLED: { text: "已取消", color: "red" },
  POSTED: { text: "已过账", color: "green" },
};

export const PARTNER_TYPE_LABELS: Record<string, string> = {
  customer: "客户",
  supplier: "供应商",
  both: "客户/供应商",
};

export const LOCATION_TYPE_LABELS: Record<string, string> = {
  WAREHOUSE: "仓库",
  ZONE: "库区",
  AISLE: "巷道",
  RACK: "货架",
  BIN: "储位",
  DOCK: "收发货区",
};

export const MOVEMENT_TYPE_LABELS: Record<string, string> = {
  RECEIVE: "收货入库",
  PUTAWAY_OUT: "上架移出",
  PUTAWAY_IN: "上架移入",
};
