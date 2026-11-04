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
        .join("; ");
    }
    if (error.response?.status === 403) return "You do not have permission for this action";
    return "The operation failed, please try again later";
  }
  if (error instanceof Error) return error.message;
  return "The operation failed, please try again later";
}

// Do not write onError: (e) => message.error(...): the thenable message returns resolves only when the toast closes,
// and React Query waits for it, so buttons keep spinning for about 3 s after an error and ignore clicks
export function showError(error: unknown): void {
  message.error(getErrorMessage(error));
}
