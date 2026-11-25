"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  CheckCircle2,
  Film,
  Wand2,
  Clock,
  Copy,
  Check,
  ShieldCheck,
  Image as ImageIcon,
  Sparkles,
  Layers,
  ZoomIn,
  X,
  Play,
  AlertCircle,
  Loader2,
} from "lucide-react";
import type { MasterScenePlan, PromptSet, ProjectImagesResponse, ShotImageAsset } from "@/lib/types";
import { resolveImageUrl } from "@/lib/api/client";

export interface ResultsViewProps {
  scenePlan: MasterScenePlan | null;
  prompts: PromptSet | null;
  reviewReport?: any | null;
  projectImages?: ProjectImagesResponse | null;
  onReset?: () => void;
  onGenerateVideo?: () => void;
  isReviewPending?: boolean;
  isGeneratingVideo?: boolean;
  videoGenerationError?: string | null;
}

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      title="Copy prompt"
      className={`flex items-center gap-1.5 px-[14px] py-1.5 rounded-lg border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] text-[12px] cursor-pointer transition-all duration-150 shrink-0 ${copied ? "text-[#22c55e]" : "text-[var(--color-text-secondary)]"
        }`}
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function getRoleBadgeStyle(role: string) {
  const upper = (role || "").toUpperCase();
  if (upper === "CHARACTER") {
    return "bg-purple-500/15 text-purple-300 border-purple-500/30";
  }
  if (upper === "PRODUCT") {
    return "bg-amber-500/15 text-amber-300 border-amber-500/30";
  }
  if (upper === "ENVIRONMENT") {
    return "bg-blue-500/15 text-blue-300 border-blue-500/30";
  }
  if (upper === "ACTION_KEYFRAME") {
    return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
  }
  return "bg-gray-500/15 text-gray-300 border-gray-500/30";
}

export function ResultsView({
  scenePlan,
  prompts,
  reviewReport,
  projectImages,
  onReset,
  onGenerateVideo,
  isReviewPending = false,
  isGeneratingVideo = false,
  videoGenerationError = null,
}: ResultsViewProps) {
  // Lightbox Modal State
  const [activeModalImage, setActiveModalImage] = useState<{
    url: string;
    label: string;
    role: string;
    reused?: boolean;
  } | null>(null);

  // Helper to retrieve shot images for a given shot_id or sequence number
  const getShotImages = (shotId: string, seq?: number): ShotImageAsset[] => {
    if (!projectImages?.shots) return [];
    const shotData = projectImages.shots.find(
      (s) => s.shot_id === shotId || (seq !== undefined && s.sequence_number === seq)
    );
    return shotData?.images || [];
  };

  const masterAssets = projectImages?.master_assets
    ? Object.entries(projectImages.master_assets)
    : [];

  return (
    <div className="flex flex-col gap-10">
      {/* Success / Review Banner */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className={`flex flex-col items-center py-10 px-6 rounded-2xl text-center gap-3 border ${
          isReviewPending
            ? "bg-purple-500/[0.06] border-purple-500/20"
            : "bg-[#22c55e]/[0.06] border-[#22c55e]/15"
        }`}
      >
        <div className={`p-4 rounded-full ${isReviewPending ? "bg-purple-500/[0.15]" : "bg-[#22c55e]/[0.12]"}`}>
          {isReviewPending ? (
            <Sparkles size={40} className="text-purple-400" />
          ) : (
            <CheckCircle2 size={40} color="#22c55e" />
          )}
        </div>
        <h2 className="text-[26px] font-bold text-[var(--color-text-primary)]">
          {isReviewPending ? "Prompts & Keyframes Ready for Review" : "Your Video Plan is Ready!"}
        </h2>
        <p className="text-[14px] text-[var(--color-text-secondary)] max-w-[560px]">
          Successfully generated{" "}
          <strong className="text-[var(--color-text-primary)]">{scenePlan?.scenes.length ?? 0} scenes</strong>,{" "}
          <strong className="text-[var(--color-text-primary)]">{prompts?.prompts.length ?? 0} optimized prompts</strong>
          {projectImages?.total_images ? (
            <span>
              {" "}and{" "}
              <strong className="text-purple-400">{projectImages.total_images} visual reference assets</strong>
            </span>
          ) : null}
          {prompts?.total_duration ? (
            <span> ({Math.round(prompts.total_duration)}s total)</span>
          ) : null}.
          {isReviewPending && (
            <span className="block mt-1.5 text-xs text-gray-400">
              Inspect the prompts and generated keyframe images below. Video rendering will only begin when you click Generate Video.
            </span>
          )}
        </p>

        {videoGenerationError && (
          <div className="mt-2 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-red-500/10 border border-red-500/25 text-red-300 text-xs max-w-lg">
            <AlertCircle size={15} className="shrink-0 text-red-400" />
            <span>{videoGenerationError}</span>
          </div>
        )}

        {isReviewPending && onGenerateVideo && (
          <div className="flex flex-wrap items-center justify-center gap-3 mt-3">
            {onReset && (
              <button
                onClick={onReset}
                disabled={isGeneratingVideo}
                className="px-6 py-2.5 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] text-[13px] font-medium cursor-pointer hover:bg-white/5 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Start New Project
              </button>
            )}
            <button
              onClick={onGenerateVideo}
              disabled={isGeneratingVideo}
              className="flex items-center gap-2 px-7 py-2.5 rounded-xl border-none bg-gradient-to-br from-blue-500 to-violet-500 text-white text-[14px] font-semibold cursor-pointer shadow-[0_4px_16px_rgba(59,130,246,0.35)] hover:opacity-90 transition disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isGeneratingVideo ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Starting Video Generation...
                </>
              ) : (
                <>
                  <Play size={15} fill="currentColor" />
                  Generate Video
                </>
              )}
            </button>
          </div>
        )}
      </motion.div>

      {/* 1. Project Master Visual Assets (Global Anchors) */}
      {masterAssets.length > 0 && (
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border-subtle)]">
            <div className="flex items-center gap-2.5">
              <Sparkles size={20} className="text-amber-400" />
              <h3 className="text-[18px] font-bold">Project Master Visual Anchors (Gemini Generated)</h3>
            </div>
            <span className="text-xs text-gray-400">
              Locked entities reused across scenes for 100% visual consistency
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
            {masterAssets.map(([assetId, path]) => {
              const fullUrl = resolveImageUrl(path);
              const isChar = assetId.toLowerCase().includes("char");
              const isProd = assetId.toLowerCase().includes("prod");
              const roleLabel = isChar ? "CHARACTER" : isProd ? "PRODUCT" : "MASTER ASSET";

              return (
                <motion.div
                  key={assetId}
                  whileHover={{ y: -3 }}
                  className="card p-3 rounded-2xl bg-[var(--color-bg-elevated)] border border-[var(--color-border-default)] flex flex-col gap-3 group relative overflow-hidden"
                >
                  <div
                    className="relative aspect-video rounded-xl overflow-hidden bg-black/40 border border-white/10 cursor-pointer"
                    onClick={() =>
                      setActiveModalImage({
                        url: fullUrl,
                        label: assetId,
                        role: roleLabel,
                        reused: false,
                      })
                    }
                  >
                    <img
                      src={fullUrl}
                      alt={assetId}
                      className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                      loading="lazy"
                    />
                    <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-1.5 text-white text-xs font-medium">
                      <ZoomIn size={16} /> Click to Inspect
                    </div>
                    <span
                      className={`absolute top-2 left-2 text-[10px] font-bold tracking-wider px-2 py-0.5 rounded-full border backdrop-blur-md ${getRoleBadgeStyle(
                        roleLabel
                      )}`}
                    >
                      {roleLabel}
                    </span>
                  </div>

                  <div className="flex items-center justify-between px-1">
                    <span className="text-sm font-semibold text-white truncate">{assetId}</span>
                    <span className="text-[11px] text-emerald-400 font-medium">Locked Master</span>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </section>
      )}

      {/* 2. Scene Plan */}
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

      {/* 3. Generated Prompts & Shot Visual References */}
      {prompts && prompts.prompts.length > 0 && (
        <section className="flex flex-col gap-4">
          <div className="flex items-center justify-between pb-3 border-b border-[var(--color-border-subtle)]">
            <div className="flex items-center gap-2.5">
              <Wand2 size={20} color="#8b5cf6" />
              <h3 className="text-[18px] font-bold">Generated Prompts & Shot Keyframes</h3>
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

          <div className="flex flex-col gap-5">
            {prompts.prompts.map((prompt, idx) => {
              let fullPromptText = prompt.prompt_text;
              if (prompt.negative_constraints) {
                fullPromptText += `\n\nNegative: ${prompt.negative_constraints}`;
              }
              // if (prompt.continuity_requirements && prompt.continuity_requirements.length > 0) {
              //   fullPromptText += `\n\nContinuity: ${prompt.continuity_requirements.join(", ")}`;
              // }

              const shotImages = getShotImages(prompt.shot_id, prompt.sequence_number || idx + 1);

              return (
                <motion.div
                  key={prompt.prompt_id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: idx * 0.05 }}
                  className="card px-5 py-[20px] flex flex-col gap-4 relative overflow-hidden rounded-2xl bg-[var(--color-bg-elevated)] border border-[var(--color-border-default)]"
                >
                  <div className="absolute left-0 top-0 bottom-0 w-[4px] bg-gradient-to-b from-blue-500 via-indigo-500 to-purple-500" />

                  {/* Top Bar */}
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] font-bold px-3 py-1 rounded-full bg-white/[0.08] text-[var(--color-text-primary)]">
                        Shot {idx + 1}
                      </span>
                      <span className="text-[12px] text-[var(--color-text-muted)] py-[3px]">
                        {prompt.duration_seconds}s · ID: {prompt.shot_id}
                      </span>
                    </div>
                    <CopyButton text={fullPromptText} />
                  </div>

                  {/* Prompt Text Box */}
                  <div className="bg-black/30 rounded-xl py-3.5 px-4 border border-[var(--color-border-subtle)]">
                    <p className="text-[13px] font-mono leading-[1.75] text-white/90 whitespace-pre-wrap">
                      {fullPromptText}
                    </p>
                  </div>

                  {/* Shot Visual Reference Images (Gemini Generated) */}
                  {shotImages.length > 0 && (
                    <div className="flex flex-col gap-2.5 pt-1">
                      <div className="flex items-center gap-2 text-xs font-semibold text-gray-300">
                        <ImageIcon size={14} className="text-purple-400" />
                        <span>Visual References for this Shot ({shotImages.length} Assets):</span>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                        {shotImages.map((img, imgIdx) => {
                          const imgUrl = resolveImageUrl(img.url || img.path);
                          return (
                            <div
                              key={`${img.asset_id}-${imgIdx}`}
                              onClick={() =>
                                setActiveModalImage({
                                  url: imgUrl,
                                  label: img.asset_id,
                                  role: img.role,
                                  reused: img.reused,
                                })
                              }
                              className="group relative aspect-video rounded-xl overflow-hidden bg-black/40 border border-white/10 hover:border-purple-500/50 cursor-pointer transition-all duration-200"
                            >
                              <img
                                src={imgUrl}
                                alt={img.asset_id}
                                className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                                loading="lazy"
                              />

                              {/* Hover Overlay */}
                              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-[11px] font-medium gap-1">
                                <ZoomIn size={14} /> View
                              </div>

                              {/* Role Badge */}
                              <span
                                className={`absolute top-1.5 left-1.5 text-[9px] font-bold tracking-wider px-1.5 py-0.5 rounded-full border backdrop-blur-md ${getRoleBadgeStyle(
                                  img.role
                                )}`}
                              >
                                {img.role}
                              </span>

                              {/* Reused Indicator */}
                              {img.reused && (
                                <span className="absolute bottom-1.5 right-1.5 text-[9px] font-semibold bg-emerald-500/80 text-white px-1.5 py-0.5 rounded shadow">
                                  Reused
                                </span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Style & Motion Badges */}
                  {(prompt.style_modifiers || prompt.motion_parameters) && (
                    <div className="flex flex-wrap gap-2 pt-1 border-t border-[var(--color-border-subtle)]">
                      {prompt.style_modifiers && (
                        <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-[#8b5cf6]/10 text-[#a78bfa] border border-[#8b5cf6]/20">
                          Style: {prompt.style_modifiers}
                        </span>
                      )}
                      {prompt.motion_parameters && (
                        <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-[#3b82f6]/10 text-[#60a5fa] border border-[#3b82f6]/20">
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
      {(onReset || onGenerateVideo) && (
        <div className="flex justify-center gap-4 pt-4">
          {onReset && (
            <button
              onClick={onReset}
              disabled={isGeneratingVideo}
              className="px-8 py-3 rounded-xl border border-[var(--color-border-default)] bg-[var(--color-bg-elevated)] text-[var(--color-text-primary)] text-[14px] font-medium cursor-pointer hover:bg-white/5 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Start New Project
            </button>
          )}
          {onGenerateVideo && (
            <button
              onClick={onGenerateVideo}
              disabled={isGeneratingVideo}
              className="flex items-center gap-2 px-8 py-3 rounded-xl border-none bg-gradient-to-br from-blue-500 to-violet-500 text-white text-[14px] font-semibold cursor-pointer shadow-[0_4px_12px_rgba(59,130,246,0.3)] hover:opacity-90 transition disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isGeneratingVideo ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Starting Video Generation...
                </>
              ) : (
                <>
                  <Play size={15} fill="currentColor" />
                  Generate Video
                </>
              )}
            </button>
          )}
        </div>
      )}

      {/* 4. Lightbox Modal for Full-Resolution Image Inspection */}
      <AnimatePresence>
        {activeModalImage && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setActiveModalImage(null)}
            className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 sm:p-6"
          >
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="relative max-w-4xl w-full max-h-[90vh] bg-gray-900 border border-gray-800 rounded-2xl overflow-hidden flex flex-col shadow-2xl"
            >
              {/* Modal Header */}
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-800 bg-gray-950/60">
                <div className="flex items-center gap-2.5">
                  <span
                    className={`text-[11px] font-bold tracking-wider px-2.5 py-0.5 rounded-full border ${getRoleBadgeStyle(
                      activeModalImage.role
                    )}`}
                  >
                    {activeModalImage.role}
                  </span>
                  <h4 className="text-sm font-semibold text-white">{activeModalImage.label}</h4>
                  {activeModalImage.reused && (
                    <span className="text-[10px] text-emerald-400 font-medium bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                      Reused Master Anchor
                    </span>
                  )}
                </div>

                <button
                  onClick={() => setActiveModalImage(null)}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>

              {/* Modal Image Body */}
              <div className="p-4 flex items-center justify-center bg-black/60 overflow-auto">
                <img
                  src={activeModalImage.url}
                  alt={activeModalImage.label}
                  className="max-h-[70vh] w-auto object-contain rounded-lg shadow-lg"
                />
              </div>

              {/* Modal Footer */}
              <div className="px-5 py-3 border-t border-gray-800 bg-gray-950/40 flex justify-between items-center text-xs text-gray-400">
                <span>Direct Asset Link:</span>
                <a
                  href={activeModalImage.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-purple-400 hover:text-purple-300 underline font-mono text-[11px]"
                >
                  Open Original High-Res
                </a>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
