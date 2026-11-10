import { useEffect, useState } from "react";

import { MaterialCommunityIcons } from "@expo/vector-icons";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";

import { Button, Card, Field } from "@/components/ui";
import { errorText } from "@/lib/api";
import { loadPhoto, removePhoto, takePhoto, type PhotoRef } from "@/lib/photos";
import { radius, space, useStyles, useTheme, type Palette } from "@/theme";

function Thumbnail({ photo, onRemove }: { photo: PhotoRef; onRemove?: () => void }) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
  const [uri, setUri] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    void loadPhoto(photo.id).then((b64) => alive && b64 && setUri(`data:image/jpeg;base64,${b64}`));
    return () => {
      alive = false;
    };
  }, [photo.id]);
  return (
    <View style={s.thumb} testID="photo-thumb">
      {uri ? (
        <Image source={{ uri }} style={s.thumbImage} accessibilityLabel={photo.caption ?? "Photo"} />
      ) : (
        <View style={[s.thumbImage, { alignItems: "center", justifyContent: "center" }]}>
          <MaterialCommunityIcons name="image-outline" size={28} color={c.textMuted} />
        </View>
      )}
      {photo.caption && (
        <Text style={s.caption} numberOfLines={2}>
          {photo.caption}
        </Text>
      )}
      {onRemove && (
        <Pressable accessibilityRole="button" accessibilityLabel="Remove photo" onPress={onRemove} hitSlop={6} style={s.remove}>
          <MaterialCommunityIcons name="close" size={18} color="#ffffff" />
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
  label = "Photos",
  hint = "Damage, labels, anything worth showing",
}: {
  photos?: PhotoRef[];
  onChange?: (photos: PhotoRef[]) => void;
  onTaken?: (photo: PhotoRef) => void;
  label?: string;
  hint?: string;
}) {
  const { c } = useTheme();
  const s = useStyles(makeStyles);
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
    <Card title={photos.length ? `${label} (${photos.length})` : label} icon="camera-outline">
      <Text style={s.hint}>{hint}</Text>
      <Field label="Note for the next photo (optional)" value={note} onChangeText={setNote} testID="photo-note" placeholder="e.g. Torn box" />
      <Button title="Take photo" variant="secondary" icon="camera" onPress={() => void take()} loading={busy} testID="take-photo" />
      {error && <Text style={{ color: c.dangerText }}>{error}</Text>}
      {photos.length > 0 && (
        <View style={s.grid}>
          {photos.map((p) => (
            <Thumbnail key={p.id} photo={p} onRemove={onChange ? () => remove(p) : undefined} />
          ))}
        </View>
      )}
    </Card>
  );
}

const makeStyles = (c: Palette) =>
  StyleSheet.create({
    hint: { fontSize: 13, color: c.textMuted, marginTop: -space.sm },
    grid: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
    thumb: { width: 96, gap: 4 },
    thumbImage: { width: 96, height: 96, borderRadius: radius.md, backgroundColor: c.surfaceAlt },
    caption: { fontSize: 12, color: c.textMuted },
    remove: {
      position: "absolute",
      top: 4,
      right: 4,
      width: 32,
      height: 32,
      borderRadius: 16,
      backgroundColor: "rgba(0,0,0,0.6)",
      alignItems: "center",
      justifyContent: "center",
    },
  });
