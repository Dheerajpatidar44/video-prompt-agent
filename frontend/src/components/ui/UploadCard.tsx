"use client";

import React, { useRef } from "react";
import { ImageIcon, X } from "lucide-react";
import Swal from "sweetalert2";

const showToast = (msg: string) => {
  Swal.fire({
    toast: true,
    position: "bottom-end",
    icon: "warning",
    title: msg,
    showConfirmButton: false,
    timer: 3000,
    timerProgressBar: true,
    background: "var(--color-bg-elevated)",
    color: "var(--color-text-primary)",
    iconColor: "#f59e0b",
    customClass: {
      popup: "border border-[var(--color-border-subtle)] rounded-xl shadow-lg",
    },
  });
};

interface UploadCardProps {
  label: string;
  description: string;
  icon: React.ReactNode;
  files?: File[];
  onFilesChange: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
  maxFiles?: number;
}

export function UploadCard({
  label,
  description,
  icon,
  files = [],
  onFilesChange,
  accept = "image/png,image/jpg,image/jpeg,image/webp",
  multiple = true,
  maxFiles = 5,
}: UploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const dropped = Array.from(e.dataTransfer.files);
    const newFiles = [...files, ...dropped];
    if (newFiles.length > maxFiles) {
      showToast(`You can only upload a maximum of ${maxFiles} files here.`);
      onFilesChange(newFiles.slice(0, maxFiles));
    } else {
      onFilesChange(newFiles);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selected = Array.from(e.target.files);
      const newFiles = [...files, ...selected];
      if (newFiles.length > maxFiles) {
        showToast(`You can only upload a maximum of ${maxFiles} files here.`);
        onFilesChange(newFiles.slice(0, maxFiles));
      } else {
        onFilesChange(newFiles);
      }
    }
  };

  const removeFile = (idx: number) => {
    onFilesChange(files.filter((_, i) => i !== idx));
  };

  return (
    <div
      className="card px-[18px] py-4 flex flex-col gap-3.5 h-full"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-[9px]">
          <span className="text-blue-500 flex items-center">{icon}</span>
          <div>
            <p className="text-[13px] font-semibold text-[var(--color-text-primary)] m-0">{label}</p>
            <p className="text-[11px] text-[var(--color-text-secondary)] mt-0.5">{description}</p>
          </div>
        </div>
      </div>

      {/* Drop Zone */}
      <div
        className="upload-zone flex-1 min-h-[110px] p-4 gap-2"
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
      >
        {files.length === 0 ? (
          <>
            <ImageIcon size={24} color="var(--color-text-muted)" />
            <p className="text-[13px] text-[var(--color-text-secondary)] text-center">
              Click to upload or drag and drop
            </p>
            <p className="text-[11px] text-[var(--color-text-muted)]">PNG, JPG, WebP (Max 10MB each)</p>
          </>
        ) : (
          <div className="flex flex-wrap gap-2 w-full">
            {files.map((f, i) => (
              <div
                key={i}
                className="relative w-[72px] h-[72px] rounded-lg overflow-hidden border border-[var(--color-border-default)]"
              >
                <img
                  src={URL.createObjectURL(f)}
                  alt={f.name}
                  className="w-full h-full object-cover"
                />
                <button
                  onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                  className="absolute top-[3px] right-[3px] bg-black/70 border-none rounded-full w-[18px] h-[18px] flex items-center justify-center cursor-pointer text-white"
                >
                  <X size={10} />
                </button>
              </div>
            ))}
            {files.length < maxFiles && (
              <div className="w-[72px] h-[72px] rounded-lg bg-white/5 border-[1.5px] border-dashed border-[var(--color-border-default)] flex items-center justify-center text-[var(--color-text-muted)] text-2xl">
                +
              </div>
            )}
          </div>
        )}
      </div>
      <input ref={inputRef} type="file" accept={accept} multiple={multiple} onChange={handleChange} className="hidden" />
    </div>
  );
}
