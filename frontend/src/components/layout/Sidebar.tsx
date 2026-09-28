"use client";

import React from "react";
import { Sparkles, FolderOpen, Layers, Settings, Plus } from "lucide-react";

interface NavItem {
  icon: React.ReactNode;
  label: string;
  id: string;
}

const navItems: NavItem[] = [
  { icon: <FolderOpen size={18} />, label: "Projects", id: "projects" },
  { icon: <Layers size={18} />, label: "Assets", id: "assets" },
  { icon: <Settings size={18} />, label: "Settings", id: "settings" },
];

export function Sidebar() {
  const [active, setActive] = React.useState("projects");

  return (
    <aside
      style={{
        width: 230,
        minHeight: "100vh",
        background: "var(--color-bg-surface)",
        borderRight: "1px solid var(--color-border-subtle)",
        display: "flex",
        flexDirection: "column",
        padding: "20px 12px",
        gap: 8,
        flexShrink: 0,
      }}
    >
      {/* Logo */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "4px 6px 20px",
        }}
      >
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 4px 12px rgba(59,130,246,0.35)",
          }}
        >
          <Sparkles size={16} color="white" />
        </div>
        <span style={{ fontWeight: 700, fontSize: 15, color: "var(--color-text-primary)", letterSpacing: "-0.02em" }}>
          Video Prompt Agent
        </span>
      </div>

      {/* New Project Button */}
      <button
        className="btn-primary"
        style={{ padding: "10px 14px", fontSize: 14, marginBottom: 8, borderRadius: 8 }}
      >
        <Plus size={16} />
        New Project
      </button>

      {/* Navigation */}
      <nav style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1 }}>
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActive(item.id)}
            className={`sidebar-nav-item ${active === item.id ? "active" : ""}`}
            style={{ background: "none", border: "none", width: "100%", textAlign: "left" }}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>
    </aside>
  );
}
