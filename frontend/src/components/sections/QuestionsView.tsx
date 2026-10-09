"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle, ChevronRight, Loader2 } from "lucide-react";
import type { Question } from "@/lib/types";

interface QuestionsViewProps {
  gaps?: any[];
  questions: Question[];
  answers: Record<string, string>;
  onAnswerChange: (id: string, value: string) => void;
  onSubmit: () => void;
  isSubmitting: boolean;
}

const priorityColor: Record<string, string> = {
  CRITICAL: "#ef4444",
  IMPORTANT: "#f59e0b",
  OPTIONAL: "#6b7280",
};

export function QuestionsView({ gaps = [], questions, answers, onAnswerChange, onSubmit, isSubmitting }: QuestionsViewProps) {
  return (
    <div className="flex flex-col gap-5">
      {/* Info Banner */}
      <div className="flex gap-3.5 px-5 py-4 bg-blue-500/10 border border-blue-500/20 rounded-xl">
        <AlertCircle size={20} color="#3b82f6" className="shrink-0 mt-[1px]" />
        <div>
          <p className="text-[14px] font-semibold text-[var(--color-text-primary)] mb-1">
            I need a few clarifications
          </p>
          <p className="text-[13px] text-[var(--color-text-secondary)] leading-[1.6]">
            To generate the most accurate video plan, please answer these questions based on the analysis of your script.
          </p>
        </div>
      </div>

      {/* Gaps Section */}
      {gaps.length > 0 && (
        <div className="flex flex-col gap-3 mb-2">
          <h3 className="text-[16px] font-semibold text-[var(--color-text-primary)] ml-1">
            Issues Identified in Script
          </h3>
          <div className="grid gap-2.5">
            {gaps.map((gap, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.05 }}
                className="px-[18px] py-[14px] bg-[var(--color-bg-elevated)] rounded-lg border-t border-r border-b border-[var(--color-border-subtle)] border-l-4 flex flex-col gap-1.5"
                style={{
                  borderLeftColor: priorityColor[gap.importance] || "#3b82f6",
                }}
              >
                <div className="flex justify-between items-center">
                  <span className="text-[14px] font-semibold text-[var(--color-text-primary)]">
                    {gap.title}
                  </span>
                  <span
                    className="text-[10px] font-bold px-2 py-0.5 rounded-full uppercase"
                    style={{
                      color: priorityColor[gap.importance] || "#3b82f6",
                      backgroundColor: `${priorityColor[gap.importance] || "#3b82f6"}1a`,
                    }}
                  >
                    {gap.importance}
                  </span>
                </div>
                <p className="text-[13px] text-[var(--color-text-secondary)] leading-[1.5]">
                  {gap.description}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* Questions */}
      {questions.map((q, idx) => (
        <motion.div
          key={q.id}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: idx * 0.07 }}
          className="card px-6 py-5 flex flex-col gap-3.5"
        >
          <div className="flex items-start gap-3">
            <span className="w-[26px] h-[26px] rounded-full bg-[var(--color-bg-overlay)] flex items-center justify-center text-[12px] font-bold text-[var(--color-text-muted)] shrink-0">
              {idx + 1}
            </span>
            <div className="flex-1">
              <p className="text-[14px] font-medium text-[var(--color-text-primary)] leading-[1.5] mb-1.5">
                {q.question}
              </p>
            </div>
          </div>

          <textarea
            className="input-area w-full px-3.5 py-3 text-[13px] leading-[1.6]"
            placeholder="Your answer..."
            rows={3}
            value={answers[q.id] || ""}
            onChange={(e) => onAnswerChange(q.id, e.target.value)}
          />
        </motion.div>
      ))}

      {/* Submit */}
      <button
        onClick={onSubmit}
        disabled={isSubmitting}
        className="btn-primary px-6 py-3.5 text-[15px] mt-2 flex justify-center items-center gap-2"
      >
        {isSubmitting ? (
          <Loader2 size={18} className="animate-spin" />
        ) : (
          <>
            Submit Answers & Generate Plan
            <ChevronRight size={18} />
          </>
        )}
      </button>
    </div>
  );
}
