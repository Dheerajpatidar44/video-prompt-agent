"use client";

import React from "react";
import { SlidersHorizontal, Clock, Monitor, Film, Camera } from "lucide-react";

export interface VideoSettingsValues {
  duration: string;
  aspectRatio: string;
  videoStyle: string;
  cameraStyle: string;
}

interface VideoSettingsProps {
  values: VideoSettingsValues;
  onChange: (values: VideoSettingsValues) => void;
}

const selectStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--color-bg-base)",
  border: "1px solid var(--color-border-default)",
  borderRadius: 7,
  color: "var(--color-text-primary)",
  fontSize: 13,
  padding: "8px 28px 8px 10px",
  outline: "none",
  cursor: "pointer",
  appearance: "none",
  backgroundImage:
    "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%238a8f9e' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 7px center",
  transition: "border-color 0.2s",
};

interface SelectFieldProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}

function SelectField({ icon, label, value, options, onChange }: SelectFieldProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--color-text-muted)", fontSize: 12, fontWeight: 500 }}>
        {icon}
        <span>{label}</span>
      </div>
      <select value={value} onChange={(e) => onChange(e.target.value)} style={selectStyle}>
        {options.map((opt) => (
          <option key={opt} value={opt} style={{ background: "#1c1f26" }}>{opt}</option>
        ))}
      </select>
    </div>
  );
}

export function VideoSettings({ values, onChange }: VideoSettingsProps) {
  const update = (key: keyof VideoSettingsValues) => (v: string) => onChange({ ...values, [key]: v });

  return (
    <div className="card" style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 14, height: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <SlidersHorizontal size={17} color="#3b82f6" />
          <div>
            <p style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)", margin: 0 }}>Video Settings</p>
            <p style={{ fontSize: 12, color: "var(--color-text-secondary)", marginTop: 2, lineHeight: 1.4 }}>
              Provide additional preferences
            </p>
          </div>
        </div>

      {/* 2×2 Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <SelectField icon={<Clock size={12} />} label="Duration" value={values.duration}
          options={["5 seconds", "10 seconds", "15 seconds", "30 seconds", "60 seconds"]} onChange={update("duration")} />
        <SelectField icon={<Monitor size={12} />} label="Aspect Ratio" value={values.aspectRatio}
          options={["16:9 (Landscape)", "9:16 (Portrait)", "1:1 (Square)", "4:3", "21:9 (Cinematic)"]} onChange={update("aspectRatio")} />
        <SelectField icon={<Film size={12} />} label="Video Style" value={values.videoStyle}
          options={["Cinematic", "Documentary", "Commercial", "Animation", "Realistic", "Artistic"]} onChange={update("videoStyle")} />
        <SelectField icon={<Camera size={12} />} label="Camera Style" value={values.cameraStyle}
          options={["Auto", "Static", "Handheld", "Drone", "Tracking Shot", "Timelapse"]} onChange={update("cameraStyle")} />
      </div>
    </div>
  );
}
