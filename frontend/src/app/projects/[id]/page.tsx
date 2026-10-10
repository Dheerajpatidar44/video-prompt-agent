"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { ResultsView } from "@/components/sections/ResultsView";
import { FinalVideoView } from "@/components/sections/FinalVideoView";
import { ApiClient } from "@/lib/api/client";
import { ArrowLeft, Sparkles, Play, Download } from "lucide-react";
import type { MasterScenePlan, PromptSet } from "@/lib/types";

export default function ProjectDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scenePlan, setScenePlan] = useState<MasterScenePlan | null>(null);
  const [prompts, setPrompts] = useState<PromptSet | null>(null);
  const [reviewReport, setReviewReport] = useState<any | null>(null);
  const [showPreviewVideo, setShowPreviewVideo] = useState(false);
  const [videoGenerating, setVideoGenerating] = useState(false);
  const [previewAspect, setPreviewAspect] = useState<number | null>(null);
  const [previewProgress, setPreviewProgress] = useState(0);

  useEffect(() => {
    if (id) {
      fetchProjectData();
    }
  }, [id]);

  const fetchProjectData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Fetch in parallel
      const [sceneRes, promptRes] = await Promise.all([
        ApiClient.getScenePlan(id),
        ApiClient.getPrompts(id)
      ]);

      if (sceneRes.scene_plan) setScenePlan(sceneRes.scene_plan);
      if (promptRes.prompt_set) setPrompts(promptRes.prompt_set);
      if (promptRes.review_report) setReviewReport(promptRes.review_report);
      
    } catch (err: any) {
      console.error(err);
      setError(err.message || "Failed to load project details");
    } finally {
      setLoading(false);
    }
  };

  const handleBack = () => {
    router.push("/projects");
  };

  return (
    <div className="flex h-screen bg-[#050505] text-white overflow-hidden font-sans">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />

        <main className={`flex-1 overflow-y-auto ${showPreviewVideo || videoGenerating ? "p-0 flex flex-col" : "p-6 md:p-8 lg:p-12"} relative z-0`}>
          {showPreviewVideo ? (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex-1 flex flex-col p-6 md:p-8 lg:p-12 items-start justify-start">
               <div 
                 className="relative cursor-pointer group rounded-3xl overflow-hidden shadow-2xl border border-gray-800 transition-all"
                 style={{ 
                   width: '200px', 
                   aspectRatio: previewAspect ? `${previewAspect}` : '16/9' 
                 }}
                 onClick={() => router.push(`/projects/${id}/video/36ff99c2-19d0-49c1-a048-d58c5fb31bb6`)}
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
                   src="/ad.mp4" 
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
                          const response = await fetch("/ad.mp4");
                          const blob = await response.blob();
                          const url = window.URL.createObjectURL(blob);
                          const link = document.createElement("a");
                          link.href = url;
                          link.download = scenePlan?.story_title ? `${scenePlan.story_title}.mp4` : "Generated_Video.mp4";
                          document.body.appendChild(link);
                          link.click();
                          document.body.removeChild(link);
                          window.URL.revokeObjectURL(url);
                        } catch (err) {
                          window.open("/ad.mp4", "_blank");
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
                         {scenePlan?.story_title || "Generated Video.mp4"}
                       </span>
                    </div>
                    {/* Progress Bar */}
                    <div className="w-full h-[2px] bg-white/30 overflow-hidden">
                       <div 
                         className="h-full bg-white transition-all duration-100 ease-linear" 
                         style={{ width: `${previewProgress}%` }}
                       ></div>
                    </div>
                 </div>
               </div>
            </motion.div>
          ) : videoGenerating ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex-1 flex flex-col items-center justify-center space-y-6"
            >
              <div className="relative">
                <div
                  className="w-20 h-20 rounded-full border-4 border-blue-500/15 border-t-blue-500 animate-spin"
                />
                <div className="absolute inset-0 flex items-center justify-center">
                  <Sparkles size={28} className="text-blue-500" />
                </div>
              </div>
              <div className="text-center">
                <h2 className="text-2xl font-bold bg-gradient-to-r from-blue-500 to-purple-500 bg-clip-text text-transparent mb-2">
                  Generating your final video...
                </h2>
                <p className="text-gray-400 text-sm">
                  Our multi-agent system is working on your project.
                </p>
              </div>
            </motion.div>
          ) : (
            <div className="max-w-6xl mx-auto space-y-8">
            <button 
              onClick={handleBack}
              className="group flex items-center gap-2 text-gray-400 hover:text-white transition-colors text-sm font-medium w-fit"
            >
              <div className="p-1.5 rounded-full bg-white/5 group-hover:bg-white/10 transition-colors">
                <ArrowLeft size={16} />
              </div>
              Back to Projects
            </button>

            {loading ? (
              <div className="flex flex-col items-center justify-center p-32 space-y-4">
                <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-[#ff3366]"></div>
                <p className="text-gray-400 font-medium">Loading project details...</p>
              </div>
            ) : error ? (
              <div className="bg-[#ff3366]/10 border border-[#ff3366]/30 rounded-2xl p-8 text-center max-w-2xl mx-auto mt-12">
                <p className="text-[#ff3366] font-medium mb-4">{error}</p>
                <button 
                  onClick={fetchProjectData}
                  className="px-6 py-2 bg-white/5 hover:bg-white/10 rounded-full text-sm font-medium transition-colors"
                >
                  Try Again
                </button>
              </div>
            ) : (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="pb-20"
              >
                <ResultsView 
                  scenePlan={scenePlan} 
                  prompts={prompts} 
                  reviewReport={reviewReport}
                  onReset={() => router.push('/')} 
                  onGenerateVideo={() => {
                    setVideoGenerating(true);
                    setTimeout(() => {
                      setVideoGenerating(false);
                      setShowPreviewVideo(true);
                    }, 3000);
                  }}
                />
              </motion.div>
            )}
          </div>
          )}
        </main>
      </div>
    </div>
  );
}
