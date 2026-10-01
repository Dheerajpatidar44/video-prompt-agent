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
    <div className="card" style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Section Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <FileText size={17} color="#3b82f6" />
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)", margin: 0 }}>
            Video Script
          </h2>
        </div>
      </div>

      {/* Tabs */}
      <div
        style={{
          display: "flex",
          gap: 3,
          background: "var(--color-bg-base)",
          padding: 3,
          borderRadius: 7,
          width: "fit-content",
          border: "1px solid var(--color-border-subtle)",
        }}
      >
        {(["paste", "upload"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "6px 13px",
              borderRadius: 5,
              fontSize: 13,
              fontWeight: 500,
              border: "none",
              cursor: "pointer",
              transition: "all 0.15s ease",
              background: mode === m ? "var(--color-bg-elevated)" : "transparent",
              color: mode === m ? "var(--color-text-primary)" : "var(--color-text-muted)",
              boxShadow: mode === m ? "0 1px 3px rgba(0,0,0,0.4)" : "none",
            }}
          >
            {m === "paste" ? <FileText size={13} /> : <Upload size={13} />}
            {m === "paste" ? "Paste Script" : "Upload File (PDF / TXT)"}
          </button>
        ))}
      </div>

      {/* Textarea or Upload zone */}
      {mode === "paste" ? (
        <div style={{ position: "relative" }}>
          <textarea
            value={scriptText}
            onChange={(e) => onScriptChange(e.target.value)}
            placeholder="Paste your video script here..."
            style={{
              width: "100%",
              height: 190,
              padding: "12px 14px",
              background: "var(--color-bg-base)",
              border: "1px solid var(--color-border-default)",
              borderRadius: 8,
              color: "var(--color-text-primary)",
              fontSize: 14,
              lineHeight: 1.75,
              fontFamily: "inherit",
              outline: "none",
              resize: "vertical",
              transition: "border-color 0.2s",
              boxSizing: "border-box",
              display: "block",
            }}
            onFocus={(e) => (e.target.style.borderColor = "rgba(59,130,246,0.5)")}
            onBlur={(e) => (e.target.style.borderColor = "var(--color-border-default)")}
          />
          <span
            style={{
              position: "absolute",
              bottom: 10,
              right: 12,
              fontSize: 11,
              color: "var(--color-text-muted)",
              pointerEvents: "none",
            }}
          >
            {scriptText.length} characters
          </span>
        </div>
      ) : (
        <div
          className="upload-zone"
          style={{ height: 190, gap: 10, flexDirection: "column", display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}
          onClick={() => fileInputRef.current?.click()}
          onDrop={handleFileDrop}
          onDragOver={(e) => e.preventDefault()}
        >
          <Upload size={22} color="var(--color-text-muted)" />
          {uploadedFile ? (
            <p style={{ fontSize: 13, color: "#3b82f6", fontWeight: 500 }}>{uploadedFile.name}</p>
          ) : (
            <>
              <p style={{ fontSize: 13, color: "var(--color-text-secondary)", fontWeight: 500 }}>Click to upload or drag and drop</p>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)" }}>PDF, TXT (Max 10MB)</p>
            </>
          )}
        </div>
      )}
      <input ref={fileInputRef} type="file" accept=".pdf,.txt" onChange={handleFileChange} style={{ display: "none" }} />
    </div>
  );
}
