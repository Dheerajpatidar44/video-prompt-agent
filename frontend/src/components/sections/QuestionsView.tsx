"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle, ChevronRight, Loader2 } from "lucide-react";
import type { Question } from "@/lib/types";

interface QuestionsViewProps {
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

export function QuestionsView({ questions, answers, onAnswerChange, onSubmit, isSubmitting }: QuestionsViewProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Info Banner */}
      <div
        style={{
          display: "flex",
          gap: 14,
          padding: "16px 20px",
          background: "rgba(59,130,246,0.08)",
          border: "1px solid rgba(59,130,246,0.2)",
          borderRadius: 12,
        }}
      >
        <AlertCircle size={20} color="#3b82f6" style={{ flexShrink: 0, marginTop: 1 }} />
        <div>
          <p style={{ fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)", marginBottom: 4 }}>
            I need a few clarifications
          </p>
          <p style={{ fontSize: 13, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
            To generate the most accurate video plan, please answer these questions based on the analysis of your script.
          </p>
        </div>
      </div>

      {/* Questions */}
      {questions.map((q, idx) => (
        <motion.div
          key={q.id}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: idx * 0.07 }}
          className="card"
          style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 14 }}
        >
          <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
            <span
              style={{
                width: 26,
                height: 26,
                borderRadius: "50%",
                background: "var(--color-bg-overlay)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                fontWeight: 700,
                color: "var(--color-text-muted)",
                flexShrink: 0,
              }}
            >
              {idx + 1}
            </span>
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: 14, fontWeight: 500, color: "var(--color-text-primary)", lineHeight: 1.5, marginBottom: 6 }}>
                {q.question}
              </p>
              <div style={{ display: "flex", gap: 6 }}>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 500,
                    padding: "2px 8px",
                    borderRadius: 99,
                    background: "var(--color-bg-overlay)",
                    color: "var(--color-text-secondary)",
                  }}
                >
                  {q.category}
                </span>
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "2px 8px",
                    borderRadius: 99,
                    color: priorityColor[q.priority] || "#6b7280",
                    background: `${priorityColor[q.priority] || "#6b7280"}1a`,
                  }}
                >
                  {q.priority}
                </span>
              </div>
            </div>
          </div>

          <textarea
            className="input-area"
            placeholder="Your answer..."
            rows={3}
            value={answers[q.id] || ""}
            onChange={(e) => onAnswerChange(q.id, e.target.value)}
            style={{ width: "100%", padding: "12px 14px", fontSize: 13, lineHeight: 1.6 }}
          />
        </motion.div>
      ))}

      {/* Submit */}
      <button
        onClick={onSubmit}
        disabled={isSubmitting}
        className="btn-primary"
        style={{ padding: "14px 24px", fontSize: 15, marginTop: 8 }}
      >
        {isSubmitting ? (
          <Loader2 size={18} style={{ animation: "spin 1s linear infinite" }} />
        ) : (
          <>
            Submit Answers & Generate Plan
            <ChevronRight size={18} />
          </>
        )}
      </button>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
