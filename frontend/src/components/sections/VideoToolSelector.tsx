"use client";

import React from "react";
import { Cpu } from "lucide-react";

const TOOLS = ["Veo", "Runway", "Kling"] as const;
type Tool = (typeof TOOLS)[number];

interface VideoToolSelectorProps {
  selectedTool: Tool;
  onToolChange: (tool: Tool) => void;
}

export function VideoToolSelector({ selectedTool, onToolChange }: VideoToolSelectorProps) {
  return (
    <div className="card" style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14, height: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
        <Cpu size={17} color="#3b82f6" />
        <div>
          <p style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)", margin: 0 }}>
            Video Generation Tool
          </p>
          <p style={{ fontSize: 12, color: "var(--color-text-secondary)", marginTop: 2, lineHeight: 1.4 }}>
            Select the tool you will use to generate the video.
          </p>
        </div>
      </div>

      {/* Tool Radio Buttons */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {TOOLS.map((tool) => {
          const isSelected = selectedTool === tool;
          return (
            <button
              key={tool}
              onClick={() => onToolChange(tool)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "8px 15px",
                borderRadius: 8,
                border: isSelected
                  ? "1.5px solid rgba(59,130,246,0.7)"
                  : "1.5px solid var(--color-border-default)",
                background: isSelected ? "rgba(59,130,246,0.1)" : "var(--color-bg-base)",
                color: isSelected ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                fontSize: 13,
                fontWeight: 500,
                cursor: "pointer",
                transition: "all 0.15s ease",
                outline: "none",
              }}
              onMouseEnter={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.borderColor = "var(--color-border-strong)";
                  e.currentTarget.style.color = "var(--color-text-primary)";
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected) {
                  e.currentTarget.style.borderColor = "var(--color-border-default)";
                  e.currentTarget.style.color = "var(--color-text-secondary)";
                }
              }}
            >
              <span
                style={{
                  width: 14,
                  height: 14,
                  borderRadius: "50%",
                  border: isSelected ? "4px solid #3b82f6" : "2px solid var(--color-text-muted)",
                  display: "inline-flex",
                  flexShrink: 0,
                  transition: "all 0.15s ease",
                }}
              />
              {tool}
            </button>
          );
        })}
      </div>
    </div>
  );
}
