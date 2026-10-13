"use client";

import React, { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkles, AlertCircle, Play, Download } from "lucide-react";

import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { ScriptInput } from "@/components/sections/ScriptInput";
import { ReferenceUploads } from "@/components/sections/ReferenceUploads";
import { VideoToolSelector } from "@/components/sections/VideoToolSelector";

import { QuestionsView } from "@/components/sections/QuestionsView";
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

  // Video View States
  const [showFullVideo, setShowFullVideo] = useState(true);
  const [previewAspect, setPreviewAspect] = useState<number | null>(null);
  const [previewProgress, setPreviewProgress] = useState(0);

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
    setShowFullVideo(true);
    setPreviewAspect(null);
    setPreviewProgress(0);
  };

  const isVideoStitching = state.isStitching || state.videoStatus === "STITCHING";
  const videoGenerating = state.status === "COMPLETED" && !state.finalVideoUrl && state.videoStatus !== "FAILED";

  const isLoading =
    state.status === "ANALYZING" ||
    state.status === "PLANNING" ||
    state.status === "GENERATING" ||
    state.status === "REVIEWING" ||
    videoGenerating;

  const showFinalVideo = !!state.finalVideoUrl;
  const showEmptyState = (state.status === "COMPLETED" || state.status === "ERROR") && state.videoStatus === "FAILED" && !state.finalVideoUrl;

  const canGenerate = (scriptText.trim().length > 0 || uploadedFile !== null) && !isLoading;

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--color-bg-base)]">
      <Sidebar />

      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className={`flex-1 overflow-y-auto min-w-0 ${showFinalVideo && showFullVideo ? "p-0" : "px-7 pt-6 pb-10"} relative z-0 flex flex-col`}>
          <AnimatePresence mode="wait">
            {showFinalVideo && state.finalVideoUrl && (
              showFullVideo ? (
                <motion.div key="final_video" variants={pageVariants} initial="initial" animate="animate" exit="exit" className="flex-1 flex flex-col h-full w-full">
                  <FinalVideoView videoUrl={state.finalVideoUrl} prompts={state.prompts?.prompts || []} totalDuration={state.prompts?.total_duration || 12} />
                </motion.div>
              ) : (
                <motion.div key="preview_video" variants={pageVariants} initial="initial" animate="animate" exit="exit" className="flex-1 flex flex-col items-start justify-start max-w-6xl mx-auto w-full pt-8">
                   <div 
                     className="relative cursor-pointer group rounded-3xl overflow-hidden shadow-2xl border border-gray-800 transition-all"
                     style={{ 
                       width: previewAspect && previewAspect < 1 ? 'auto' : '350px',
                       height: previewAspect && previewAspect < 1 ? '380px' : 'auto',
                       aspectRatio: previewAspect ? `${previewAspect}` : '16/9' 
                     }}
                     onClick={() => setShowFullVideo(true)}
                     onMouseEnter={(e) => {
                       const video = e.currentTarget.querySelector('video');
                       if (video) video.play();
                     }}
                     onMouseLeave={(e) => {
                       const video = e.currentTarget.querySelector('video');
                       if (video) {
                         video.pause();
                         video.currentTime = 0;
                         setPreviewProgress(0);
                       }
                     }}
                   >
                     <video 
                       src={state.finalVideoUrl} 
                       className="w-full h-full object-cover" 
                       muted 
                       playsInline 
                       onLoadedMetadata={(e) => {
                         const w = e.currentTarget.videoWidth;
                         const h = e.currentTarget.videoHeight;
                         if (w && h) setPreviewAspect(w / h);
                       }}
                       onTimeUpdate={(e) => {
                         const video = e.currentTarget;
                         const progress = (video.currentTime / (video.duration || 1)) * 100;
                         setPreviewProgress(progress);
                       }}
                     />
                     
                     {/* Default Play Icon (Hidden on Hover) */}
                     <div className="absolute top-4 left-4 w-9 h-9 rounded-full bg-white/20 backdrop-blur-md flex items-center justify-center opacity-100 group-hover:opacity-0 transition-opacity duration-300">
                       <Play size={16} className="text-white ml-0.5" fill="currentColor" />
                     </div>

                     {/* Top Right Download Button (Visible on Hover) */}
                     <div className="absolute top-4 right-4 w-9 h-9 bg-[#e0deda] backdrop-blur-md rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity translate-y-[-5px] group-hover:translate-y-0 duration-300">
                        <button 
                          className="text-gray-800 hover:text-black transition-all hover:scale-110 cursor-pointer w-full h-full flex items-center justify-center" 
                          onClick={async (e) => { 
                            e.stopPropagation(); 
                            try {
                              const response = await fetch(state.finalVideoUrl!);
                              const blob = await response.blob();
                              const url = window.URL.createObjectURL(blob);
                              const link = document.createElement("a");
                              link.href = url;
                              link.download = "Generated_Video.mp4";
                              document.body.appendChild(link);
                              link.click();
                              document.body.removeChild(link);
                              window.URL.revokeObjectURL(url);
                            } catch (err) {
                              window.open(state.finalVideoUrl!, "_blank");
                            }
                          }}
                        >
                          <Download size={16} />
                        </button>
                     </div>

                     {/* Bottom Gradient & Text (Visible on Hover) */}
                     <div className="absolute bottom-0 left-0 right-0 h-1/2 bg-gradient-to-t from-black/80 via-black/40 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-5">
                        <div className="flex items-center gap-3 mb-3">
                           <div className="w-6 h-6 rounded-full border-2 border-white flex items-center justify-center shrink-0">
                             <Play size={10} className="text-white ml-0.5" fill="currentColor" />
                           </div>
                           <span className="text-white font-semibold text-[15px] truncate">
                             Generated Video.mp4
                           </span>
                        </div>
                        {/* Progress Bar */}
                        <div className="w-full h-[2px] bg-white/30 overflow-hidden">
                           <div 
                             className="h-full bg-white transition-all duration-75"
                             style={{ width: `${previewProgress}%` }}
                           />
                        </div>
                     </div>
                   </div>
                </motion.div>
              )
            )}

            {showEmptyState && (
               <motion.div key="empty_state" variants={pageVariants} initial="initial" animate="animate" exit="exit" className="flex flex-col items-center justify-center p-32 space-y-4 text-center">
                 <div className="bg-gray-900/50 p-4 rounded-full border border-gray-800 mb-2">
                   <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-gray-500">
                     <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect>
                     <line x1="7" y1="2" x2="7" y2="22"></line>
                     <line x1="17" y1="2" x2="17" y2="22"></line>
                     <line x1="2" y1="12" x2="22" y2="12"></line>
                     <line x1="2" y1="7" x2="7" y2="7"></line>
                     <line x1="2" y1="17" x2="7" y2="17"></line>
                     <line x1="17" y1="17" x2="22" y2="17"></line>
                     <line x1="17" y1="7" x2="22" y2="7"></line>
                   </svg>
                 </div>
                 <h3 className="text-xl font-medium text-white">No Video Available</h3>
                 <p className="text-gray-400 max-w-md">
                   This project could not generate a valid video or all shots failed. Please try again with a different prompt.
                 </p>
                 <button onClick={reset} className="mt-6 px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded-full text-white font-medium transition">
                   Start Over
                 </button>
               </motion.div>
            )}

            {/* ---- Main Input Form ---- */}
            {state.status === "IDLE" && !showFinalVideo && !showEmptyState && (
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
                    {isVideoStitching
                      ? "Stitching scenes into final video..."
                      : videoGenerating
                        ? `Rendering video shots (${state.completedShots || 0}/${state.totalShots || 0} completed)...`
                        : state.status === "ANALYZING"
                          ? "Analyzing your script..."
                          : state.status === "PLANNING"
                            ? "Drafting master scene plan..."
                            : state.status === "GENERATING"
                              ? "Generating visual prompts..."
                              : "Reviewing and polishing prompts..."}
                  </h2>
                  <p className="text-[var(--color-text-secondary)] text-sm">
                    {isVideoStitching
                      ? "FFmpeg is merging your completed shots into a high-definition video."
                      : "Our multi-agent system is working on your project."}
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

            {/* ResultsView (Prompts) removed as requested */}

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
