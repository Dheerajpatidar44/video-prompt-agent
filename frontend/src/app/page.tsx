"use client";

import React, { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkles, AlertCircle } from "lucide-react";

import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { ScriptInput } from "@/components/sections/ScriptInput";
import { ReferenceUploads } from "@/components/sections/ReferenceUploads";
import { VideoToolSelector } from "@/components/sections/VideoToolSelector";

import { QuestionsView } from "@/components/sections/QuestionsView";
import { ResultsView } from "@/components/sections/ResultsView";
import { useVideoAgent } from "@/hooks/useVideoAgent";

const pageVariants = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3 } },
  exit: { opacity: 0, y: -12, transition: { duration: 0.2 } },
};

export default function HomePage() {
  // Form State
  const [scriptText, setScriptText] = useState("");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [characterFiles, setCharacterFiles] = useState<File[]>([]);
  const [productFiles, setProductFiles] = useState<File[]>([]);
  const [brandFiles, setBrandFiles] = useState<File[]>([]);
  const [selectedTool, setSelectedTool] = useState<any>("Veo");

  // Agent Logic
  const { state, analyzeScript, submitAnswers, setAnswer, reset } = useVideoAgent();

  const handleGenerate = () => {
    if (!scriptText.trim() && !uploadedFile) return;
    analyzeScript(
      uploadedFile ?? undefined, 
      scriptText.trim() || undefined,
      selectedTool,
      characterFiles,
      productFiles,
      brandFiles
    );
  };

  const handleReset = () => {
    reset();
    setScriptText("");
    setUploadedFile(null);
    setCharacterFiles([]);
    setProductFiles([]);
    setBrandFiles([]);
  };

  const isLoading =
    state.status === "ANALYZING" ||
    state.status === "PLANNING" ||
    state.status === "GENERATING";

  const canGenerate = (scriptText.trim().length > 0 || uploadedFile !== null) && !isLoading;

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        overflow: "hidden",
        background: "var(--color-bg-base)",
      }}
    >
      <Sidebar />

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <Header />

        <main
          style={{
            flex: 1,
            padding: "24px 28px 40px",
            overflowY: "auto",
            minWidth: 0,
          }}
        >
          <AnimatePresence mode="wait">
            {/* ---- Main Input Form ---- */}
            {state.status === "IDLE" && (
              <motion.div key="form" variants={pageVariants} initial="initial" animate="animate" exit="exit">
                <div
                  style={{
                    maxWidth: 1100,
                    margin: "0 auto",
                    display: "flex",
                    flexDirection: "column",
                    gap: 20,
                  }}
                >
                  {/* Reference Uploads & Tool Selector: 4 equal columns */}
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(4, 1fr)",
                      gap: 16,
                      alignItems: "stretch",
                    }}
                  >
                    <ReferenceUploads
                      characterFiles={characterFiles}
                      productFiles={productFiles}
                      brandFiles={brandFiles}
                      onCharacterFilesChange={setCharacterFiles}
                      onProductFilesChange={setProductFiles}
                      onBrandFilesChange={setBrandFiles}
                    />
                    <VideoToolSelector selectedTool={selectedTool} onToolChange={setSelectedTool} />
                  </div>

                  {/* Script Input */}
                  <ScriptInput
                    scriptText={scriptText}
                    onScriptChange={setScriptText}
                    uploadedFile={uploadedFile}
                    onFileUpload={setUploadedFile}
                  />

                  {/* Generate Button */}
                  <button
                    id="generate-btn"
                    onClick={handleGenerate}
                    disabled={!canGenerate}
                    className="btn-primary"
                    style={{
                      padding: "16px 40px",
                      fontSize: 16,
                      borderRadius: 12,
                      opacity: canGenerate ? 1 : 0.5,
                      cursor: canGenerate ? "pointer" : "not-allowed",
                      alignSelf: "center",
                      marginTop: 12,
                    }}
                  >
                    <Sparkles size={20} />
                    Generate Video Prompt
                    <span style={{ marginLeft: 4, opacity: 0.8 }}>→</span>
                  </button>
                </div>
              </motion.div>
            )}

            {/* ---- Loading State ---- */}
            {isLoading && (
              <motion.div
                key="loading"
                variants={pageVariants}
                initial="initial"
                animate="animate"
                exit="exit"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  minHeight: "60vh",
                  gap: 24,
                  textAlign: "center",
                }}
              >
                <div style={{ position: "relative" }}>
                  <div
                    style={{
                      width: 80,
                      height: 80,
                      borderRadius: "50%",
                      border: "3px solid rgba(59,130,246,0.15)",
                      borderTop: "3px solid #3b82f6",
                      animation: "spin 1s linear infinite",
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <Sparkles size={28} color="#3b82f6" />
                  </div>
                </div>
                <div>
                  <h2
                    style={{
                      fontSize: 24,
                      fontWeight: 700,
                      background: "linear-gradient(135deg, #3b82f6, #8b5cf6)",
                      WebkitBackgroundClip: "text",
                      WebkitTextFillColor: "transparent",
                      marginBottom: 8,
                    }}
                  >
                    {state.status === "ANALYZING"
                      ? "Analyzing your script..."
                      : state.status === "PLANNING"
                        ? "Drafting master scene plan..."
                        : "Generating visual prompts..."}
                  </h2>
                  <p style={{ color: "var(--color-text-secondary)", fontSize: 14 }}>
                    Our multi-agent system is working on your project.
                  </p>
                </div>
                <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
              </motion.div>
            )}

            {/* ---- Questions ---- */}
            {state.status === "WAITING_FOR_USER" && (
              <motion.div key="questions" variants={pageVariants} initial="initial" animate="animate" exit="exit">
                <div style={{ maxWidth: 760, margin: "0 auto" }}>
                  <QuestionsView
                    gaps={state.gaps}
                    questions={state.questions}
                    answers={state.answers}
                    onAnswerChange={setAnswer}
                    onSubmit={submitAnswers}
                    isSubmitting={state.isSubmitting}
                  />
                </div>
              </motion.div>
            )}

            {/* ---- Results ---- */}
            {state.status === "COMPLETED" && (
              <motion.div key="results" variants={pageVariants} initial="initial" animate="animate" exit="exit">
                <div style={{ maxWidth: 1000, margin: "0 auto" }}>
                  <ResultsView scenePlan={state.scenePlan} prompts={state.prompts} onReset={handleReset} />
                </div>
              </motion.div>
            )}

            {/* ---- Error ---- */}
            {state.status === "ERROR" && (
              <motion.div
                key="error"
                variants={pageVariants}
                initial="initial"
                animate="animate"
                exit="exit"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  minHeight: "50vh",
                  gap: 16,
                  textAlign: "center",
                }}
              >
                <div
                  style={{
                    padding: 20,
                    background: "rgba(239,68,68,0.1)",
                    borderRadius: "50%",
                  }}
                >
                  <AlertCircle size={40} color="#ef4444" />
                </div>
                <h3 style={{ fontSize: 20, fontWeight: 700 }}>Something went wrong</h3>
                <p style={{ color: "var(--color-text-secondary)", maxWidth: 420 }}>{state.error}</p>
                <button
                  onClick={handleReset}
                  style={{
                    marginTop: 8,
                    padding: "12px 28px",
                    borderRadius: 10,
                    background: "#ef4444",
                    color: "white",
                    border: "none",
                    fontWeight: 600,
                    fontSize: 14,
                    cursor: "pointer",
                  }}
                >
                  Try Again
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </main>
      </div>
    </div>
  );
}
