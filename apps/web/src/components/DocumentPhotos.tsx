import { useEffect, useState } from "react";

import { CameraOutlined, DeleteOutlined, UploadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Drawer, Empty, Image, Popconfirm, Spin, Typography, Upload, message } from "antd";
import dayjs from "dayjs";

import { apiClient } from "@/api/client";
import { showError } from "@/api/errors";
import type { Attachment } from "@/api/types";

// No imports from ui/documents: DocTitle in ui.tsx renders PhotosButton, and that would make an import cycle

const MAX_BYTES = 4 * 1024 * 1024;

/** The image needs the sign-in header, so it is fetched as a blob instead of a plain <img src> */
function useImageUrl(id: string): string | undefined {
  const { data: blob } = useQuery({
    queryKey: ["attachment-content", id],
    queryFn: async () => (await apiClient.get<Blob>(`/attachments/${id}/content`, { responseType: "blob" })).data,
    staleTime: Infinity, // a stored photo never changes
  });
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    if (!blob) return;
    const objectUrl = URL.createObjectURL(blob);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob]);
  return url;
}

function Photo({ photo, onDelete }: { photo: Attachment; onDelete: () => void }) {
  const url = useImageUrl(photo.id);
  return (
    <div className="wms-photo">
      {url ? <Image src={url} alt={photo.caption ?? photo.file_name} width={150} height={150} style={{ objectFit: "cover" }} /> : <Spin />}
      <div className="wms-photo-meta">
        {photo.caption && <Typography.Text strong>{photo.caption}</Typography.Text>}
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {photo.created_by ?? "—"} · {dayjs(photo.created_at + "Z").format("YYYY-MM-DD HH:mm")}
        </Typography.Text>
      </div>
      <Popconfirm title="Delete this photo?" onConfirm={onDelete}>
        <Button type="text" size="small" danger icon={<DeleteOutlined />} aria-label={`Delete ${photo.file_name}`} />
      </Popconfirm>
    </div>
  );
}

const toBase64 = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });

/** Photos of a document (damage on receipt, what a count found, ...): taken on the PDA or uploaded here */
export function PhotosButton({ documentId, title }: { documentId: string; title: string }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const queryKey = ["documents", documentId, "attachments"];
  const { data, isError, isLoading } = useQuery({
    queryKey,
    queryFn: async () => (await apiClient.get<Attachment[]>(`/documents/${documentId}/attachments`)).data,
    retry: false,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      if (file.size > MAX_BYTES) throw new Error("The photo is larger than 4 MB");
      await apiClient.post(`/documents/${documentId}/attachments`, { content_base64: await toBase64(file) });
    },
    onSuccess: () => {
      message.success("Photo added");
      void refresh();
    },
    onError: showError,
  });
  const remove = useMutation({
    mutationFn: async (id: string) => apiClient.delete(`/attachments/${id}`),
    onSuccess: () => void refresh(),
    onError: showError,
  });

  if (isError) return null; // no access to this document's photos
  const count = data?.length ?? 0;
  return (
    <>
      <Button type="text" size="small" icon={<CameraOutlined />} onClick={() => setOpen(true)} loading={isLoading}>
        Photos{count ? ` (${count})` : ""}
      </Button>
      <Drawer open={open} onClose={() => setOpen(false)} title={`Photos · ${title}`} size={560} destroyOnHidden>
        <Upload
          accept="image/jpeg,image/png,image/webp"
          showUploadList={false}
          beforeUpload={(file) => {
            upload.mutate(file);
            return false;
          }}
        >
          <Button icon={<UploadOutlined />} loading={upload.isPending}>
            Add photo
          </Button>
        </Upload>
        <div className="wms-photo-grid" data-testid="document-photos">
          {count === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No photos yet. They can be taken on the PDA." />}
          <Image.PreviewGroup>
            {data?.map((photo) => (
              <Photo key={photo.id} photo={photo} onDelete={() => remove.mutate(photo.id)} />
            ))}
          </Image.PreviewGroup>
        </div>
      </Drawer>
    </>
  );
}
