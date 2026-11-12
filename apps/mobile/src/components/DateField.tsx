import { Field } from "@/components/ui";
import { parseDate } from "@/lib/inbound";

/**
 * Date as YYYY-MM-DD from digits only: the number pad opens and the dashes are inserted while typing (20271231 ->
 * 2027-12-31), so no separators are typed. A scanned or pasted YYYY-MM-DD works too. Usually
 * filled by scanning the carton's GS1 code or our stock label instead.
 */
export function DateField({ label, value, onChange, testID }: { label: string; value: string; onChange: (value: string) => void; testID?: string }) {
  const complete = value.length === 10;
  return (
    <Field
      label={label}
      placeholder="YYYY-MM-DD"
      keyboardType="number-pad"
      maxLength={10}
      value={value}
      onChangeText={(text) => onChange(formatDate(text))}
      error={complete && !parseDate(value) ? "Not a real date" : null}
      testID={testID}
    />
  );
}

export function formatDate(text: string): string {
  const d = text.replace(/\D/g, "").slice(0, 8);
  if (d.length <= 4) return d;
  if (d.length <= 6) return `${d.slice(0, 4)}-${d.slice(4)}`;
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}`;
}
