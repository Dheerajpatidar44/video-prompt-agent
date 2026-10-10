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
import { FinalVideoView } from "@/components/sections/FinalVideoView";
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
  const [showFinalVideo, setShowFinalVideo] = useState(false);
  const [videoGenerating, setVideoGenerating] = useState(false);

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
    setShowFinalVideo(false);
    setVideoGenerating(false);
  };

  const isLoading =
    state.status === "ANALYZING" ||
    state.status === "PLANNING" ||
    state.status === "GENERATING" ||
    state.status === "REVIEWING" ||
    videoGenerating;

  const canGenerate = (scriptText.trim().length > 0 || uploadedFile !== null) && !isLoading;

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-bg-base)]">
      <Sidebar />

      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className={`flex-1 overflow-y-auto min-w-0 ${showFinalVideo ? "p-0" : "px-7 pt-6 pb-10"}`}>
          <AnimatePresence mode="wait">
            {showFinalVideo && (
               <motion.div key="final_video" variants={pageVariants} initial="initial" animate="animate" exit="exit" className="h-full">
                 <FinalVideoView />
               </motion.div>
            )}

            {/* ---- Main Input Form ---- */}
            {state.status === "IDLE" && !showFinalVideo && (
              <motion.div key="form" variants={pageVariants} initial="initial" animate="animate" exit="exit">
                <div className="max-w-[1100px] mx-auto flex flex-col gap-5">
                  {/* Reference Uploads & Tool Selector: 4 equal columns */}
                  <div className="grid grid-cols-4 gap-4 items-stretch">
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
                    className={`btn-primary px-10 py-4 text-base rounded-xl self-center mt-3 flex items-center gap-2 ${canGenerate ? "opacity-100 cursor-pointer" : "opacity-50 cursor-not-allowed"}`}
                  >
                    <Sparkles size={20} />
                    Generate Video Prompt
                    <span className="ml-1 opacity-80">→</span>
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
                className="flex flex-col items-center justify-center min-h-[60vh] gap-6 text-center"
              >
                <div className="relative">
                  <div className="w-20 h-20 rounded-full border-[3px] border-blue-500/15 border-t-blue-500 animate-spin" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Sparkles size={28} color="#3b82f6" />
                  </div>
                </div>
                <div>
                  <h2 className="text-2xl font-bold bg-gradient-to-br from-blue-500 to-violet-500 bg-clip-text text-transparent mb-2">
                    {videoGenerating
                      ? "Generating your final video..."
                      : state.status === "ANALYZING"
                        ? "Analyzing your script..."
                        : state.status === "PLANNING"
                          ? "Drafting master scene plan..."
                          : state.status === "GENERATING"
                            ? "Generating visual prompts..."
                            : "Reviewing and polishing prompts..."}
                  </h2>
                  <p className="text-[var(--color-text-secondary)] text-sm">
                    Our multi-agent system is working on your project.
                  </p>
                </div>
              </motion.div>
            )}

            {/* ---- Questions ---- */}
            {state.status === "WAITING_FOR_USER" && (
              <motion.div key="questions" variants={pageVariants} initial="initial" animate="animate" exit="exit">
                <div className="max-w-[760px] mx-auto">
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

            {state.status === "COMPLETED" && !showFinalVideo && !videoGenerating && (
              <motion.div key="results" variants={pageVariants} initial="initial" animate="animate" exit="exit">
                <div className="max-w-[1000px] mx-auto">
                  <ResultsView 
                    scenePlan={state.scenePlan} 
                    prompts={state.prompts} 
                    reviewReport={state.reviewReport} 
                    onReset={handleReset} 
                    onGenerateVideo={() => {
                      setVideoGenerating(true);
                      setTimeout(() => {
                        setVideoGenerating(false);
                        setShowFinalVideo(true);
                      }, 3000);
                    }} 
                  />
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
                className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-center"
              >
                <div className="p-5 bg-red-500/10 rounded-full">
                  <AlertCircle size={40} color="#ef4444" />
                </div>
                <h3 className="text-xl font-bold">Something went wrong</h3>
                <p className="text-[var(--color-text-secondary)] max-w-[420px]">{state.error}</p>
                <button
                  onClick={handleReset}
                  className="mt-2 px-7 py-3 rounded-xl bg-red-500 text-white font-semibold text-sm cursor-pointer border-none hover:bg-red-600 transition-colors"
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
