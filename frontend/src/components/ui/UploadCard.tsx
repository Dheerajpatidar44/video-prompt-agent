"use client";

import React, { useRef } from "react";
import { ImageIcon, X } from "lucide-react";

interface UploadCardProps {
  label: string;
  description: string;
  icon: React.ReactNode;
  files?: File[];
  onFilesChange: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
}

export function UploadCard({
  label,
  description,
  icon,
  files = [],
  onFilesChange,
  accept = "image/png,image/jpg,image/jpeg,image/webp",
  multiple = true,
}: UploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const dropped = Array.from(e.dataTransfer.files);
    onFilesChange([...files, ...dropped]);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      onFilesChange([...files, ...Array.from(e.target.files)]);
    }
  };

  const removeFile = (idx: number) => {
    onFilesChange(files.filter((_, i) => i !== idx));
  };

  return (
    <div
      className="card"
      style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14, height: "100%" }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "9px" }}>
          <span style={{ color: "#3b82f6", display: "flex", alignItems: "center" }}>{icon}</span>
          <div>
            <p style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)", margin: 0 }}>{label}</p>
            <p style={{ fontSize: 11, color: "var(--color-text-secondary)", marginTop: 1 }}>{description}</p>
          </div>
        </div>
      </div>

      {/* Drop Zone */}
      <div
        className="upload-zone"
        style={{ flex: 1, minHeight: 110, padding: "16px", gap: 8 }}
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        {files.length === 0 ? (
          <>
            <ImageIcon size={24} color="var(--color-text-muted)" />
            <p style={{ fontSize: 13, color: "var(--color-text-secondary)", textAlign: "center" }}>
              Click to upload or drag and drop
            </p>
            <p style={{ fontSize: 11, color: "var(--color-text-muted)" }}>PNG, JPG, WebP (Max 10MB each)</p>
          </>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, width: "100%" }}>
            {files.map((f, i) => (
              <div
                key={i}
                style={{
                  position: "relative",
                  width: 72,
                  height: 72,
                  borderRadius: 8,
                  overflow: "hidden",
                  border: "1px solid var(--color-border-default)",
                }}
              >
                <img
                  src={URL.createObjectURL(f)}
                  alt={f.name}
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
                <button
                  onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                  style={{
                    position: "absolute",
                    top: 3,
                    right: 3,
                    background: "rgba(0,0,0,0.7)",
                    border: "none",
                    borderRadius: "50%",
                    width: 18,
                    height: 18,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    cursor: "pointer",
                    color: "white",
                  }}
                >
                  <X size={10} />
                </button>
              </div>
            ))}
            <div
              style={{
                width: 72,
                height: 72,
                borderRadius: 8,
                background: "rgba(255,255,255,0.03)",
                border: "1.5px dashed var(--color-border-default)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-text-muted)",
                fontSize: 24,
              }}
            >
              +
            </div>
          </div>
        )}
      </div>
      <input ref={inputRef} type="file" accept={accept} multiple={multiple} onChange={handleChange} style={{ display: "none" }} />
    </div>
  );
}
