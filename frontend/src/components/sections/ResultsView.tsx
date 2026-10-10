"use client";

import React from "react";
import { motion } from "framer-motion";
import { CheckCircle2, Film, Wand2, Clock, Copy, Check, ShieldCheck } from "lucide-react";
import type { MasterScenePlan, PromptSet } from "@/lib/types";

interface ResultsViewProps {
  scenePlan: MasterScenePlan | null;
  prompts: PromptSet | null;
  reviewReport?: any | null;
  onReset: () => void;
  onGenerateVideo: () => void;
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
      className={`flex items-center gap-1.5 px-[14px] py-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] text-[12px] cursor-pointer transition-all duration-150 shrink-0 ${
        copied ? "text-[#22c55e]" : "text-[var(--color-text-secondary)]"
      }`}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

export function ResultsView({ scenePlan, prompts, reviewReport, onReset, onGenerateVideo }: ResultsViewProps) {
  return (
    <div className="flex flex-col gap-10">
      {/* Success Banner */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex flex-col items-center py-10 px-6 bg-[#22c55e]/[0.06] border border-[#22c55e]/15 rounded-2xl text-center gap-3"
      >
        <div className="p-4 bg-[#22c55e]/[0.12] rounded-full">
          <CheckCircle2 size={40} color="#22c55e" />
        </div>
        <h2 className="text-[26px] font-bold text-[var(--color-text-primary)]">Your Video Plan is Ready!</h2>
        <p className="text-[14px] text-[var(--color-text-secondary)] max-w-[500px]">
          Successfully generated{" "}
          <strong className="text-[var(--color-text-primary)]">{scenePlan?.scenes.length ?? 0} scenes</strong> and{" "}
          <strong className="text-[var(--color-text-primary)]">{prompts?.prompts.length ?? 0} optimized prompts</strong>.
        </p>
        
      </motion.div>

      {/* Scene Plan */}
      {scenePlan && scenePlan.scenes.length > 0 && (
        <section className="flex flex-col gap-4">
          <div className="flex items-center gap-2.5 pb-3 border-b border-[var(--color-border-subtle)]">
            <Film size={20} color="#3b82f6" />
            <h3 className="text-[18px] font-bold">Master Scene Plan</h3>
          </div>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-4">
            {scenePlan.scenes.map((scene) => (
              <motion.div
                key={scene.scene_id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className="card px-5 py-[18px] flex flex-col gap-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-bold">Scene {scene.scene_number}</span>
                  <span className="text-[11px] text-[var(--color-text-muted)] flex items-center gap-1">
                    <Clock size={11} /> {scene.duration_seconds}s
                  </span>
                </div>
                <p className="text-[13px] text-[var(--color-text-secondary)] leading-[1.6]">{scene.purpose}</p>
                <div className="pt-2.5 border-t border-[var(--color-border-subtle)] flex justify-between text-[12px] text-[var(--color-text-muted)]">
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
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border-subtle)]">
            <div className="flex items-center gap-2.5">
              <Wand2 size={20} color="#8b5cf6" />
              <h3 className="text-[18px] font-bold">Generated Prompts</h3>
            </div>
            {reviewReport && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#22c55e]/10 border border-[#22c55e]/20">
                <ShieldCheck size={14} color="#22c55e" />
                <span className="text-[12px] font-semibold text-[#22c55e]">
                  QA {reviewReport.status.replace(/_/g, " ")}
                </span>
              </div>
            )}
          </div>
          <div className="flex flex-col gap-3.5">
            {prompts.prompts.map((prompt, idx) => {
              let fullPromptText = prompt.prompt_text;
              if (prompt.negative_constraints) {
                fullPromptText += `\n\nNegative: ${prompt.negative_constraints}`;
              }
              if (prompt.continuity_requirements && prompt.continuity_requirements.length > 0) {
                fullPromptText += `\n\nContinuity: ${prompt.continuity_requirements.join(', ')}`;
              }

              return (
                <motion.div
                  key={prompt.prompt_id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.05 }}
                  className="card px-5 py-[18px] flex flex-col gap-3.5 relative overflow-hidden"
                >
                  <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-gradient-to-b from-blue-500 to-violet-500" />

                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex gap-2">
                      <span className="text-[12px] font-semibold px-2.5 py-[3px] rounded-full bg-white/[0.07] text-[var(--color-text-secondary)]">
                        Prompt {idx + 1}
                      </span>
                      <span className="text-[12px] text-[var(--color-text-muted)] py-[3px]">
                        {prompt.duration_seconds}s · {prompt.camera_parameters}
                      </span>
                    </div>
                    <CopyButton text={fullPromptText} />
                  </div>

                  <div className="bg-[var(--color-bg-elevated)] rounded-lg py-3.5 px-4 border border-[var(--color-border-subtle)]">
                    <p className="text-[13px] font-mono leading-[1.75] text-white/85 whitespace-pre-wrap">
                      {fullPromptText}
                    </p>
                  </div>

                {(prompt.style_modifiers || prompt.motion_parameters) && (
                  <div className="flex flex-wrap gap-2">
                    {prompt.style_modifiers && (
                      <span className="text-[12px] px-3 py-1 rounded-full bg-[#8b5cf6]/10 text-[#a78bfa] border border-[#8b5cf6]/20">
                        Style: {prompt.style_modifiers}
                      </span>
                    )}
                    {prompt.motion_parameters && (
                      <span className="text-[12px] px-3 py-1 rounded-full bg-[#3b82f6]/10 text-[#60a5fa] border border-[#3b82f6]/20">
                        Motion: {prompt.motion_parameters}
                      </span>
                    )}
                  </div>
                )}
              </motion.div>
            );
          })}
          </div>
        </section>
      )}
 
      {/* Actions */}
      <div className="flex justify-center gap-4 pt-4">
        <button
          onClick={onReset}
          className="px-8 py-3 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] text-[14px] font-medium cursor-pointer"
        >
          Start New Project
        </button>
        <button
          onClick={onGenerateVideo}
          className="px-8 py-3 rounded-lg border-none bg-gradient-to-br from-blue-500 to-violet-500 text-white text-[14px] font-medium cursor-pointer shadow-[0_4px_12px_rgba(59,130,246,0.3)]"
        >
          Generate Final Video
        </button>
      </div>
    </div>
  );
}
