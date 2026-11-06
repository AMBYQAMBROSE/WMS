import { useEffect, useState } from "react";

import { Image, Pressable, Text, View } from "react-native";

import { Button, Field, colors, styles } from "@/components/ui";
import { errorText } from "@/lib/api";
import { loadPhoto, removePhoto, takePhoto, type PhotoRef } from "@/lib/photos";

function Thumbnail({ photo, onRemove }: { photo: PhotoRef; onRemove?: () => void }) {
  const [uri, setUri] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    void loadPhoto(photo.id).then((b64) => alive && b64 && setUri(`data:image/jpeg;base64,${b64}`));
    return () => {
      alive = false;
    };
  }, [photo.id]);
  return (
    <View style={{ width: 96, gap: 2 }} testID="photo-thumb">
      {uri ? (
        <Image source={{ uri }} style={{ width: 96, height: 96, borderRadius: 6 }} accessibilityLabel={photo.caption ?? "Photo"} />
      ) : (
        <View style={{ width: 96, height: 96, borderRadius: 6, backgroundColor: colors.muted }} />
      )}
      {photo.caption && <Text style={styles.hint} numberOfLines={2}>{photo.caption}</Text>}
      {onRemove && (
        <Pressable onPress={onRemove}>
          <Text style={{ color: colors.danger }}>Remove</Text>
        </Pressable>
      )}
    </View>
  );
}

/**
 * "Take photo" with an optional note, for evidence such as damaged goods. With onChange the photos are collected for
 * a document still being entered (they go with its submit); with onTaken each photo is handed over at once.
 */
export default function PhotoCapture({
  photos = [],
  onChange,
  onTaken,
  label = "Photos (damage, labels, ...)",
}: {
  photos?: PhotoRef[];
  onChange?: (photos: PhotoRef[]) => void;
  onTaken?: (photo: PhotoRef) => void;
  label?: string;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const take = async () => {
    setBusy(true);
    setError(null);
    try {
      const photo = await takePhoto(note);
      if (!photo) return;
      setNote("");
      onChange?.([...photos, photo]);
      onTaken?.(photo);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = (photo: PhotoRef) => {
    void removePhoto(photo.id);
    onChange?.(photos.filter((p) => p.id !== photo.id));
  };

  return (
    <View style={{ gap: 6 }}>
      <Text style={styles.title}>{label}</Text>
      <Field label="Note for the next photo (optional)" value={note} onChangeText={setNote} testID="photo-note" />
      <Button title="Take photo" variant="default" onPress={() => void take()} loading={busy} testID="take-photo" />
      {error && <Text style={{ color: colors.danger }}>{error}</Text>}
      {photos.length > 0 && (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {photos.map((p) => (
            <Thumbnail key={p.id} photo={p} onRemove={onChange ? () => remove(p) : undefined} />
          ))}
        </View>
      )}
    </View>
  );
}
