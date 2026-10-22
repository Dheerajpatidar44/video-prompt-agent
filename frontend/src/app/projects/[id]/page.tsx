"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
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
  const [videoStatus, setVideoStatus] = useState<any>(null);
  const [showFullVideo, setShowFullVideo] = useState(true);
  const [previewAspect, setPreviewAspect] = useState<number | null>(null);
  const [previewProgress, setPreviewProgress] = useState(0);

  useEffect(() => {
    if (!id) return;

    let isMounted = true;
    let interval: NodeJS.Timeout | null = null;

    // 1. Fetch prompts only once on initial load (prompts are static)
    ApiClient.getPrompts(id)
      .then((promptRes) => {
        if (isMounted && promptRes?.prompt_set) {
          setPrompts(promptRes.prompt_set);
        }
      })
      .catch(() => {});

    // 2. Poll video status only while actively generating
    const checkVideoStatus = async () => {
      try {
        setError(null);
        const vData = await ApiClient.getVideoStatus(id).catch(() => null);

        if (!isMounted) return;

        if (vData && vData.status) {
          setVideoStatus(vData);

          // Stop polling if video is completed, failed, or ready
          const isDone =
            vData.final_video_url ||
            vData.status === "COMPLETED" ||
            vData.status === "FAILED" ||
            (vData.status === "PARTIAL_FAILURE" && vData.jobs?.some((j: any) => j.status === "COMPLETED"));

          if (isDone && interval) {
            clearInterval(interval);
            interval = null;
          }
        } else {
          // Fallback for legacy project or no active video jobs
          setVideoStatus({ status: "COMPLETED", final_video_url: null });
          if (interval) {
            clearInterval(interval);
            interval = null;
          }
        }
      } catch (err: any) {
        if (isMounted) {
          console.error(err);
          setError(err.message || "Failed to load project details");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    // First immediate check
    checkVideoStatus().then(() => {
      // Only start interval if still generating and mounted
      if (isMounted) {
        interval = setInterval(checkVideoStatus, 5000);
      }
    });

    return () => {
      isMounted = false;
      if (interval) clearInterval(interval);
    };
  }, [id]);

  const handleBack = () => {
    router.push("/projects");
  };

  return (
    <div className="flex h-screen bg-[#050505] text-white overflow-hidden font-sans">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />

        <main className={`flex-1 overflow-y-auto ${showFullVideo ? "p-0" : "p-6 md:p-8 lg:p-12"} relative z-0 flex flex-col`}>
          {loading && !videoStatus ? (
             <div className="flex flex-col items-center justify-center p-32 space-y-4">
               <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-[#ff3366]"></div>
               <p className="text-gray-400 font-medium">Loading project details...</p>
             </div>
          ) : (videoStatus?.status === 'COMPLETED' || videoStatus?.status === 'PARTIAL_FAILURE') && (videoStatus?.final_video_url || videoStatus?.jobs?.find((j: any) => j.status === 'COMPLETED')?.video_url) ? (
             showFullVideo ? (
               <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex-1 flex flex-col h-full">
                 <FinalVideoView 
                   videoUrl={videoStatus.final_video_url || videoStatus.jobs.find((j: any) => j.status === 'COMPLETED').video_url} 
                   prompts={prompts?.prompts || []} 
                   totalDuration={prompts?.total_duration || 12} 
                 />
               </motion.div>
             ) : (
               <div className="max-w-6xl mx-auto w-full space-y-8">
                 <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex-1 flex flex-col items-start justify-start">
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
                       src={videoStatus.final_video_url || videoStatus.jobs.find((j: any) => j.status === 'COMPLETED').video_url} 
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
                              const urlToFetch = videoStatus.final_video_url || videoStatus.jobs.find((j: any) => j.status === 'COMPLETED').video_url;
                              const response = await fetch(urlToFetch);
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
                              window.open(videoStatus.final_video_url || videoStatus.jobs.find((j: any) => j.status === 'COMPLETED').video_url, "_blank");
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
                             className="h-full bg-white transition-all duration-100 ease-linear" 
                             style={{ width: `${previewProgress}%` }}
                           ></div>
                        </div>
                     </div>
                   </div>
                 </motion.div>
               </div>
             )
          ) : (videoStatus?.status === 'COMPLETED' || videoStatus?.status === 'PARTIAL_FAILURE' || videoStatus?.status === 'FAILED') ? (
             <div className="flex flex-col items-center justify-center p-32 space-y-4 text-center">
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
                 This project does not have a generated video. It may be a legacy project or the video generation failed.
               </p>
               <button
                 onClick={() => router.push("/")}
                 className="mt-4 px-6 py-2.5 bg-blue-600 hover:bg-blue-700 rounded-xl text-white font-medium text-sm transition cursor-pointer"
               >
                 Create New Video
               </button>
             </div>
          ) : (
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
                  {videoStatus?.completed_shots > 0 && videoStatus?.completed_shots === videoStatus?.total_shots && !videoStatus?.final_video_url
                    ? "Stitching your final video..."
                    : `Generating video shots (${videoStatus?.completed_shots || 0}/${videoStatus?.total_shots || 0} completed)...`}
                </h2>
                <p className="text-gray-400 text-sm">
                  {videoStatus?.completed_shots > 0 && videoStatus?.completed_shots === videoStatus?.total_shots && !videoStatus?.final_video_url
                    ? "FFmpeg is merging all generated scenes into a final continuous video."
                    : "Our multi-agent system is working on your project."}
                </p>
              </div>
            </motion.div>
          )}
        </main>
      </div>
    </div>
  );
}
