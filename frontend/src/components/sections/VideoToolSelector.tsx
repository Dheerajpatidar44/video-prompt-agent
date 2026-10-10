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
    <div className="card px-[18px] py-4 flex flex-col gap-3.5 h-full">
      {/* Header */}
      <div className="flex items-center gap-[9px]">
        <Cpu size={17} color="#3b82f6" />
        <div>
          <p className="text-[14px] font-semibold text-[var(--color-text-primary)] m-0">
            Video Generation Tool
          </p>
          <p className="text-[12px] text-[var(--color-text-secondary)] mt-0.5 leading-[1.4]">
            Select the tool you will use to generate the video.
          </p>
        </div>
      </div>

      {/* Tool Radio Buttons */}
      <div className="flex flex-wrap gap-2">
        {TOOLS.map((tool) => {
          const isSelected = selectedTool === tool;
          return (
            <button
              key={tool}
              onClick={() => onToolChange(tool)}
              className={`flex items-center gap-2 px-[15px] py-2 rounded-lg text-[13px] font-medium cursor-pointer transition-all duration-150 ease-in-out outline-none border-[1.5px] ${
                isSelected
                  ? "border-blue-500/70 bg-blue-500/10 text-[var(--color-text-primary)]"
                  : "border-[var(--color-border-default)] bg-[var(--color-bg-base)] text-[var(--color-text-secondary)] hover:border-[var(--color-border-strong)] hover:text-[var(--color-text-primary)]"
              }`}
            >
              <span
                className={`w-3.5 h-3.5 rounded-full inline-flex shrink-0 transition-all duration-150 ease-in-out ${
                  isSelected ? "border-4 border-blue-500" : "border-2 border-[var(--color-text-muted)]"
                }`}
              />
              {tool}
            </button>
          );
        })}
      </div>
    </div>
  );
}
