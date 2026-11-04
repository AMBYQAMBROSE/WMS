import TransferForm from "@/components/TransferForm";

export default function MoveCreatePage() {
  return <TransferForm path="moves" docLabel="Move" targetTypes={["BIN", "DOCK"]} targetLabel="Target location" />;
}
