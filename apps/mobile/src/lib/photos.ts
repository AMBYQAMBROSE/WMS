import * as Crypto from "expo-crypto";
import { ImageManipulator, SaveFormat } from "expo-image-manipulator";
import * as ImagePicker from "expo-image-picker";

import { loadLarge, removeLarge, saveLarge } from "@/lib/largeStore";

/**
 * Photos taken on the PDA (damaged goods, what a count found). They wait in the submit queue like any other work, so
 * the image is kept in file storage (AsyncStorage is far too small) and the queue holds only this reference.
 */
export interface PhotoRef {
  id: string;
  caption: string | null;
}

// Long side in pixels: enough to read a label or see damage, small enough for Wi-Fi in a warehouse (~200-400 KB)
const MAX_SIDE = 1600;
const JPEG_QUALITY = 0.7;

const keyOf = (id: string) => `photo.${id}`;

/** Opens the camera; null when the operator cancelled or did not allow the camera */
export async function takePhoto(caption: string | null): Promise<PhotoRef | null> {
  const permission = await ImagePicker.requestCameraPermissionsAsync();
  if (!permission.granted) throw new Error("The camera is not allowed for this app; allow it in the PDA settings");
  const result = await ImagePicker.launchCameraAsync({ mediaTypes: "images", quality: 1 });
  if (result.canceled || !result.assets?.length) return null;

  const asset = result.assets[0];
  const context = ImageManipulator.manipulate(asset.uri);
  if (Math.max(asset.width, asset.height) > MAX_SIDE) {
    context.resize(asset.width >= asset.height ? { width: MAX_SIDE, height: null } : { width: null, height: MAX_SIDE });
  }
  const image = await context.renderAsync();
  const saved = await image.saveAsync({ format: SaveFormat.JPEG, compress: JPEG_QUALITY, base64: true });
  if (!saved.base64) throw new Error("The photo could not be read");

  const ref: PhotoRef = { id: Crypto.randomUUID(), caption: caption?.trim() || null };
  await saveLarge(keyOf(ref.id), saved.base64);
  return ref;
}

/** Base64 JPEG for showing or sending; null if it was already sent and removed */
export const loadPhoto = (id: string) => loadLarge(keyOf(id));

export const removePhoto = (id: string) => removeLarge(keyOf(id));
