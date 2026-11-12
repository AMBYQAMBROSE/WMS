import TransferScreen from "@/components/TransferScreen";

/** Putaway without a sheet: scan the dock, the items and the target bins freely */
export default function FreePutawayScreen() {
  return <TransferScreen kind="putaway" />;
}
