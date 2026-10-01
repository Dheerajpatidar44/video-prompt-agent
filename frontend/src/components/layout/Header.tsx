"use client";

import React from "react";
import { Bell } from "lucide-react";

export function Header() {
  return (
    <header
      style={{
        height: 58,
        background: "var(--color-bg-surface)",
        borderBottom: "1px solid var(--color-border-subtle)",
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        padding: "0 24px",
        gap: 12,
        flexShrink: 0,
      }}
    >
      {/* Notification Bell */}
      <button
        style={{
          width: 36,
          height: 36,
          borderRadius: "50%",
          background: "var(--color-bg-elevated)",
          border: "1px solid var(--color-border-default)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "pointer",
          color: "var(--color-text-secondary)",
          transition: "all 0.15s ease",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.color = "var(--color-text-primary)")}
        onMouseLeave={(e) => (e.currentTarget.style.color = "var(--color-text-secondary)")}
      >
        <Bell size={16} />
      </button>

      {/* User Avatar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "5px 10px 5px 5px",
          borderRadius: 99,
          background: "var(--color-bg-elevated)",
          border: "1px solid var(--color-border-default)",
          cursor: "pointer",
        }}
      >
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: "50%",
            background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 12,
            fontWeight: 700,
            color: "white",
          }}
        >
          D
        </div>
        <span style={{ fontSize: 13, fontWeight: 500, color: "var(--color-text-primary)" }}>Dheeraj</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-muted)" strokeWidth="2">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </div>
    </header>
  );
}
