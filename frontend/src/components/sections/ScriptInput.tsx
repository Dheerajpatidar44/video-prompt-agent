"use client";

import React, { useRef } from "react";
import { FileText, Upload } from "lucide-react";

type InputMode = "paste" | "upload";

interface ScriptInputProps {
  scriptText: string;
  onScriptChange: (text: string) => void;
  uploadedFile: File | null;
  onFileUpload: (file: File | null) => void;
}

export function ScriptInput({ scriptText, onScriptChange, uploadedFile, onFileUpload }: ScriptInputProps) {
  const [mode, setMode] = React.useState<InputMode>("paste");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files?.[0];
    if (file) onFileUpload(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onFileUpload(e.target.files?.[0] ?? null);
  };

  return (
    <div className="card px-[18px] py-4 flex flex-col gap-3.5">
      {/* Section Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-[9px]">
          <FileText size={17} color="#3b82f6" />
          <h2 className="text-[14px] font-semibold text-[var(--color-text-primary)] m-0">
            Video Script
          </h2>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-[3px] bg-[var(--color-bg-base)] p-[3px] rounded-[7px] w-fit border border-[var(--color-border-subtle)]">
        {(["paste", "upload"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`flex items-center gap-1.5 px-[13px] py-1.5 rounded-[5px] text-[13px] font-medium border-none cursor-pointer transition-all duration-150 ease-in-out ${
              mode === m
                ? "bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] shadow-sm"
                : "bg-transparent text-[var(--color-text-muted)]"
            }`}
          >
            {m === "paste" ? <FileText size={13} /> : <Upload size={13} />}
            {m === "paste" ? "Paste Script" : "Upload File (PDF / TXT)"}
          </button>
        ))}
      </div>

      {/* Textarea or Upload zone */}
      {mode === "paste" ? (
        <div className="relative">
          <textarea
            value={scriptText}
            onChange={(e) => onScriptChange(e.target.value)}
            placeholder="Paste your video script here..."
            className="w-full h-[190px] px-3.5 py-3 bg-[var(--color-bg-base)] border border-[var(--color-border-default)] focus:border-blue-500/50 rounded-lg text-[var(--color-text-primary)] text-sm leading-[1.75] font-inherit outline-none resize-y transition-colors box-border block"
          />
          <span className="absolute bottom-2.5 right-3 text-[11px] text-[var(--color-text-muted)] pointer-events-none">
            {scriptText.length} characters
          </span>
        </div>
      ) : (
        <div
          className="upload-zone h-[190px] gap-2.5 flex flex-col items-center justify-center cursor-pointer"
          onClick={() => fileInputRef.current?.click()}
          onDrop={handleFileDrop}
          onDragOver={(e) => e.preventDefault()}
        >
          <Upload size={22} color="var(--color-text-muted)" />
          {uploadedFile ? (
            <p className="text-[13px] text-blue-500 font-medium">{uploadedFile.name}</p>
          ) : (
            <>
              <p className="text-[13px] text-[var(--color-text-secondary)] font-medium">Click to upload or drag and drop</p>
              <p className="text-[12px] text-[var(--color-text-muted)]">PDF, TXT (Max 10MB)</p>
            </>
          )}
        </div>
      )}
      <input ref={fileInputRef} type="file" accept=".pdf,.txt" onChange={handleFileChange} className="hidden" />
    </div>
  );
}
