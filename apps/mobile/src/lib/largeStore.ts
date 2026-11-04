import AsyncStorage from "@react-native-async-storage/async-storage";
import { File, Paths } from "expo-file-system";
import { Platform } from "react-native";

/**
 * Local storage for large data (PDA master data: several MB with tens of thousands of items).
 * AsyncStorage on Android defaults to 6MB total and about 2MB per read, which is not enough, so:
 * - Native: written to a file, no size limit
 * - Web preview: no file system, so it is chunked into AsyncStorage (browser localStorage has its own quota; for development only)
 */
const CHUNK = 500_000;
const fileOf = (key: string) => new File(Paths.document, `${key}.json`);

export async function saveLarge(key: string, text: string): Promise<void> {
  if (Platform.OS !== "web") {
    await fileOf(key).write(text);
    return;
  }
  const count = Math.ceil(text.length / CHUNK);
  const pairs: [string, string][] = [];
  for (let i = 0; i < count; i++) pairs.push([`${key}.${i}`, text.slice(i * CHUNK, (i + 1) * CHUNK)]);
  await removeLarge(key);
  await AsyncStorage.multiSet([...pairs, [`${key}.count`, String(count)]]);
}

export async function loadLarge(key: string): Promise<string | null> {
  try {
    if (Platform.OS !== "web") {
      const file = fileOf(key);
      return file.exists ? await file.text() : null;
    }
    const count = Number(await AsyncStorage.getItem(`${key}.count`));
    if (!count) return null;
    const parts = await AsyncStorage.multiGet(Array.from({ length: count }, (_, i) => `${key}.${i}`));
    return parts.map(([, v]) => v ?? "").join("");
  } catch {
    return null;
  }
}

export async function removeLarge(key: string): Promise<void> {
  if (Platform.OS !== "web") {
    const file = fileOf(key);
    if (file.exists) file.delete();
    return;
  }
  const count = Number(await AsyncStorage.getItem(`${key}.count`));
  if (count) {
    await AsyncStorage.multiRemove([...Array.from({ length: count }, (_, i) => `${key}.${i}`), `${key}.count`]);
  }
}
