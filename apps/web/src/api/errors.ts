import { message } from "antd";
import { isAxiosError } from "axios";

interface ValidationIssue {
  loc: (string | number)[];
  msg: string;
}

export function getErrorMessage(error: unknown): string {
  if (isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return (detail as ValidationIssue[])
        .map((issue) => `${issue.loc.slice(1).join(".")}: ${issue.msg}`)
        .join("；");
    }
    if (error.response?.status === 403) return "没有操作权限";
    return "操作失败，请稍后重试";
  }
  if (error instanceof Error) return error.message;
  return "操作失败，请稍后重试";
}

// 不能写成 onError: (e) => message.error(...)：message 返回的 thenable 要等提示框关闭才 resolve，
// React Query 会等它，导致按钮在出错后还转圈约 3 秒、期间点击无效
export function showError(error: unknown): void {
  message.error(getErrorMessage(error));
}
