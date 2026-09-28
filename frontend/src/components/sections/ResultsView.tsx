"use client";

import React from "react";
import { motion } from "framer-motion";
import { CheckCircle2, Film, Wand2, Clock, Copy, Check } from "lucide-react";
import type { MasterScenePlan, PromptSet } from "@/lib/types";

interface ResultsViewProps {
  scenePlan: MasterScenePlan | null;
  prompts: PromptSet | null;
  onReset: () => void;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = React.useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      title="Copy prompt"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 14px",
        borderRadius: 8,
        border: "1px solid var(--color-border-default)",
        background: "var(--color-bg-elevated)",
        color: copied ? "#22c55e" : "var(--color-text-secondary)",
        fontSize: 12,
        cursor: "pointer",
        transition: "all 0.15s",
        flexShrink: 0,
      }}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

export function ResultsView({ scenePlan, prompts, onReset }: ResultsViewProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 40 }}>
      {/* Success Banner */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "40px 24px",
          background: "rgba(34,197,94,0.06)",
          border: "1px solid rgba(34,197,94,0.15)",
          borderRadius: 16,
          textAlign: "center",
          gap: 12,
        }}
      >
        <div style={{ padding: 16, background: "rgba(34,197,94,0.12)", borderRadius: "50%" }}>
          <CheckCircle2 size={40} color="#22c55e" />
        </div>
        <h2 style={{ fontSize: 26, fontWeight: 700, color: "var(--color-text-primary)" }}>Your Video Plan is Ready!</h2>
        <p style={{ fontSize: 14, color: "var(--color-text-secondary)", maxWidth: 500 }}>
          Successfully generated{" "}
          <strong style={{ color: "var(--color-text-primary)" }}>{scenePlan?.scenes.length ?? 0} scenes</strong> and{" "}
          <strong style={{ color: "var(--color-text-primary)" }}>{prompts?.prompts.length ?? 0} optimized prompts</strong>.
        </p>
      </motion.div>

      {/* Scene Plan */}
      {scenePlan && scenePlan.scenes.length > 0 && (
        <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: 12, borderBottom: "1px solid var(--color-border-subtle)" }}>
            <Film size={20} color="#3b82f6" />
            <h3 style={{ fontSize: 18, fontWeight: 700 }}>Master Scene Plan</h3>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
            {scenePlan.scenes.map((scene) => (
              <motion.div
                key={scene.scene_id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="card"
                style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 12 }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span style={{ fontSize: 13, fontWeight: 700 }}>Scene {scene.scene_number}</span>
                  <span style={{ fontSize: 11, color: "var(--color-text-muted)", display: "flex", alignItems: "center", gap: 4 }}>
                    <Clock size={11} /> {scene.duration_seconds}s
                  </span>
                </div>
                <p style={{ fontSize: 13, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>{scene.purpose}</p>
                <div style={{ paddingTop: 10, borderTop: "1px solid var(--color-border-subtle)", display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--color-text-muted)" }}>
                  <span>{scene.shots?.length ?? 0} shots</span>
                  <span>{scene.location}</span>
                </div>
              </motion.div>
            ))}
          </div>
        </section>
      )}

      {/* Prompts */}
      {prompts && prompts.prompts.length > 0 && (
        <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, paddingBottom: 12, borderBottom: "1px solid var(--color-border-subtle)" }}>
            <Wand2 size={20} color="#8b5cf6" />
            <h3 style={{ fontSize: 18, fontWeight: 700 }}>Generated Prompts</h3>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {prompts.prompts.map((prompt, idx) => (
              <motion.div
                key={prompt.prompt_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="card"
                style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 14, position: "relative", overflow: "hidden" }}
              >
                <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 3, background: "linear-gradient(to bottom, #3b82f6, #8b5cf6)" }} />

                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
                  <div style={{ display: "flex", gap: 8 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, padding: "3px 10px", borderRadius: 99, background: "rgba(255,255,255,0.07)", color: "var(--color-text-secondary)" }}>
                      Prompt {idx + 1}
                    </span>
                    <span style={{ fontSize: 12, color: "var(--color-text-muted)", padding: "3px 0" }}>
                      {prompt.duration_seconds}s · {prompt.camera_parameters}
                    </span>
                  </div>
                  <CopyButton text={prompt.prompt_text} />
                </div>

                <div style={{ background: "var(--color-bg-elevated)", borderRadius: 8, padding: "14px 16px", border: "1px solid var(--color-border-subtle)" }}>
                  <p style={{ fontSize: 13, fontFamily: "monospace", lineHeight: 1.75, color: "rgba(255,255,255,0.85)" }}>
                    {prompt.prompt_text}
                  </p>
                </div>

                {(prompt.style_modifiers || prompt.motion_parameters) && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {prompt.style_modifiers && (
                      <span style={{ fontSize: 12, padding: "4px 12px", borderRadius: 99, background: "rgba(139,92,246,0.1)", color: "#a78bfa", border: "1px solid rgba(139,92,246,0.2)" }}>
                        Style: {prompt.style_modifiers}
                      </span>
                    )}
                    {prompt.motion_parameters && (
                      <span style={{ fontSize: 12, padding: "4px 12px", borderRadius: 99, background: "rgba(59,130,246,0.1)", color: "#60a5fa", border: "1px solid rgba(59,130,246,0.2)" }}>
                        Motion: {prompt.motion_parameters}
                      </span>
                    )}
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </section>
      )}

      {/* Reset */}
      <div style={{ display: "flex", justifyContent: "center", paddingTop: 16 }}>
        <button
          onClick={onReset}
          style={{ padding: "12px 32px", borderRadius: 10, border: "1px solid var(--color-border-default)", background: "var(--color-bg-elevated)", color: "var(--color-text-primary)", fontSize: 14, fontWeight: 500, cursor: "pointer" }}
        >
          Start New Project
        </button>
      </div>
    </div>
  );
}
