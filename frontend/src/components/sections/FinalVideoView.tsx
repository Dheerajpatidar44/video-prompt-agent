import React, { useState, useRef, useEffect } from "react";
import { 
  Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, Maximize, Repeat, 
  Download, Wrench, Sparkles, X, Copy, Check, Image as ImageIcon, ZoomIn, ExternalLink 
} from "lucide-react";

import type { GeneratedPrompt, ProjectImagesResponse, ShotImageAsset } from "@/lib/types";
import { resolveImageUrl } from "@/lib/api/client";

function formatTime(seconds: number): string {
  if (isNaN(seconds) || seconds <= 0) return "00:00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  const cs = Math.floor((seconds % 1) * 100);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}:${cs.toString().padStart(2, '0')}`;
}

export function FinalVideoView({ 
  videoUrl, 
  prompts = [], 
  totalDuration,
  projectImages,
}: { 
  videoUrl: string; 
  prompts?: GeneratedPrompt[]; 
  totalDuration?: number; 
  projectImages?: ProjectImagesResponse | null;
}) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [isLooping, setIsLooping] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrentTime] = useState("00:00:00");
  const [activeLightboxImage, setActiveLightboxImage] = useState<{
    url: string;
    label: string;
    role: string;
    reused?: boolean;
  } | null>(null);

  const getRoleBadgeStyle = (role: string) => {
    switch (role?.toUpperCase()) {
      case "CHARACTER":
        return "bg-pink-500/15 text-pink-300 border-pink-500/30";
      case "PRODUCT":
        return "bg-amber-500/15 text-amber-300 border-amber-500/30";
      case "ENVIRONMENT":
        return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
      case "ACTION_KEYFRAME":
        return "bg-blue-500/15 text-blue-300 border-blue-500/30";
      default:
        return "bg-purple-500/15 text-purple-300 border-purple-500/30";
    }
  };

  const promptsDuration = prompts.reduce((sum, p) => sum + (p.duration_seconds || 0), 0);
  const initialDuration = totalDuration && totalDuration > 0 ? totalDuration : (promptsDuration > 0 ? promptsDuration : 0);

  const [duration, setDuration] = useState<number>(initialDuration);
  const [durationStr, setDurationStr] = useState<string>(formatTime(initialDuration));
  const animationRef = useRef<number>(0);
  const [isDragging, setIsDragging] = useState(false);
  const timelineRef = useRef<HTMLDivElement>(null);
  const [selectedPart, setSelectedPart] = useState("part1");
  const [isFixPanelOpen, setIsFixPanelOpen] = useState(false);
  const [isPromptsModalOpen, setIsPromptsModalOpen] = useState(false);
  const [copiedAll, setCopiedAll] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [videoAspect, setVideoAspect] = useState<number | null>(null);

  const handleCopyAll = () => {
    const allText = prompts.map((p, idx) => {
      let text = `--- SHOT ${p.sequence_number || idx + 1} (${p.duration_seconds}s) ---\n${p.prompt_text}`;
      if (p.negative_constraints) text += `\nNegative: ${p.negative_constraints}`;
      if (p.continuity_requirements && p.continuity_requirements.length > 0) {
        text += `\nContinuity: ${p.continuity_requirements.join(', ')}`;
      }
      return text;
    }).join("\n\n");
    navigator.clipboard.writeText(allText);
    setCopiedAll(true);
    setTimeout(() => setCopiedAll(false), 2000);
  };

  // Exact duration from video metadata or prompts; completely dynamic
  const effectiveDuration = duration > 0 ? duration : (promptsDuration > 0 ? promptsDuration : 1);
  const totalSeconds = Math.max(1, Math.round(effectiveDuration));
  const frameCount = Math.max(4, Math.min(10, totalSeconds * 2));

  // Smart tick intervals so ticks never crowd together regardless of video duration
  const tickStep = totalSeconds > 30 ? 5 : totalSeconds > 15 ? 2 : 1;
  const tickIndices: number[] = [];
  for (let s = 0; s < totalSeconds; s += tickStep) {
    tickIndices.push(s);
  }
  if (!tickIndices.includes(totalSeconds)) {
    tickIndices.push(totalSeconds);
  }

  const parts = [];
  let currentStart = 0;
  for (let i = 0; i < prompts.length; i++) {
    const p = prompts[i];
    parts.push({
      id: `part${i + 1}`,
      label: `Part ${i + 1} (${currentStart.toFixed(1)}s - ${(currentStart + p.duration_seconds).toFixed(1)}s)`,
      start: currentStart,
      end: currentStart + p.duration_seconds
    });
    currentStart += p.duration_seconds;
  }
  if (parts.length === 0) {
    parts.push({
      id: "part1",
      label: `Full Video (0.0s - ${effectiveDuration.toFixed(1)}s)`,
      start: 0,
      end: effectiveDuration
    });
  }
  
  const togglePlay = () => {
    if (videoRef.current) {
      if (videoRef.current.paused) {
        const playPromise = videoRef.current.play();
        if (playPromise !== undefined) {
          playPromise.catch((error) => {
            // Auto-play was prevented or interrupted, this is fine
            console.log("Play interrupted:", error);
          });
        }
        setIsPlaying(true);
      } else {
        videoRef.current.pause();
        setIsPlaying(false);
      }
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore keydown auto-repeat when key is held down
      if (e.repeat) return;
      
      // Allow spacebar only if we aren't typing in an input
      if (e.code === 'Space' && (e.target as HTMLElement).tagName !== 'INPUT' && (e.target as HTMLElement).tagName !== 'TEXTAREA') {
        e.preventDefault();
        togglePlay();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const toggleMute = () => {
    if (videoRef.current) {
      videoRef.current.muted = !isMuted;
      setIsMuted(!isMuted);
    }
  };

  const toggleLoop = () => {
    if (videoRef.current) {
      videoRef.current.loop = !isLooping;
      setIsLooping(!isLooping);
    }
  };

  const skipForward = () => {
    if (videoRef.current) {
      videoRef.current.currentTime += 5;
    }
  };

  const skipBackward = () => {
    if (videoRef.current) {
      videoRef.current.currentTime -= 5;
    }
  };

  const toggleFullScreen = () => {
    if (videoRef.current) {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else {
        videoRef.current.requestFullscreen();
      }
    }
  };

  const downloadVideo = async () => {
    try {
      const response = await fetch(videoUrl);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'final_video.mp4';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      window.open(videoUrl, "_blank");
    }
  };

  useEffect(() => {
    if (videoRef.current && videoRef.current.duration && !isNaN(videoRef.current.duration) && videoRef.current.duration > 0) {
      setDuration(videoRef.current.duration);
      setDurationStr(formatTime(videoRef.current.duration));
    } else if (totalDuration && totalDuration > 0) {
      setDuration(totalDuration);
      setDurationStr(formatTime(totalDuration));
    } else if (promptsDuration > 0) {
      setDuration(promptsDuration);
      setDurationStr(formatTime(promptsDuration));
    }
  }, [videoUrl, totalDuration, promptsDuration]);

  const updateTimeLoop = () => {
    if (videoRef.current) {
      const current = videoRef.current.currentTime;
      const dur = videoRef.current.duration || effectiveDuration;
      setProgress((current / dur) * 100);
      setCurrentTime(formatTime(current));
    }
    animationRef.current = requestAnimationFrame(updateTimeLoop);
  };

  useEffect(() => {
    if (isPlaying) {
      animationRef.current = requestAnimationFrame(updateTimeLoop);
    } else {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    }
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, [isPlaying]);

  const handleTimeUpdate = () => {
    if (!isPlaying && !isDragging && videoRef.current) {
      const current = videoRef.current.currentTime;
      const dur = videoRef.current.duration || effectiveDuration;
      setProgress((current / dur) * 100);
      setCurrentTime(formatTime(current));
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      const d = videoRef.current.duration;
      if (d && !isNaN(d) && isFinite(d) && d > 0) {
        setDuration(d);
        setDurationStr(formatTime(d));
      }
      const w = videoRef.current.videoWidth;
      const h = videoRef.current.videoHeight;
      if (w && h) {
        setVideoAspect(w / h);
      }
    }
  };

  const updateVideoTimeFromMouse = (clientX: number) => {
    if (timelineRef.current && videoRef.current) {
      const rect = timelineRef.current.getBoundingClientRect();
      const padding = 8; // 0.5rem
      let clickX = clientX - rect.left - padding;
      const maxWidth = rect.width - padding * 2;
      if (clickX < 0) clickX = 0;
      if (clickX > maxWidth) clickX = maxWidth;
      
      const percentage = clickX / maxWidth;
      const dur = videoRef.current.duration || effectiveDuration;
      const newTime = percentage * dur;
      
      videoRef.current.currentTime = newTime;
      setProgress(percentage * 100);
      setCurrentTime(formatTime(newTime));
    }
  };

  const handleTimelineMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    updateVideoTimeFromMouse(e.clientX);
  };

  useEffect(() => {
    const handleTimelineMouseMove = (e: MouseEvent) => {
      if (isDragging) {
        updateVideoTimeFromMouse(e.clientX);
      }
    };
    const handleTimelineMouseUp = () => {
      setIsDragging(false);
    };

    if (isDragging) {
      window.addEventListener('mousemove', handleTimelineMouseMove);
      window.addEventListener('mouseup', handleTimelineMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleTimelineMouseMove);
      window.removeEventListener('mouseup', handleTimelineMouseUp);
    };
  }, [isDragging]);

  return (
    <div className={`flex h-full w-full text-white p-2 relative transition-all duration-[700ms] ease-[cubic-bezier(0.16,1,0.3,1)] ${isFixPanelOpen ? 'gap-6' : 'gap-0'}`}>
      
      {/* Left Column: Video, Controls & Timeline */}
      <div className="flex-1 flex flex-col bg-black overflow-hidden h-full p-2 transition-all duration-[700ms] ease-[cubic-bezier(0.16,1,0.3,1)]">
        
        {/* Top Section: Video Player */}
        <div className="flex-1 flex items-center justify-center min-h-0 mb-6 mt-4">
          <video 
            ref={videoRef}
            className="rounded-lg object-contain cursor-pointer shadow-[0_0_30px_rgba(0,0,0,0.5)] transition-all duration-[700ms] ease-[cubic-bezier(0.16,1,0.3,1)] mx-auto"
            style={{
              width: videoAspect ? (videoAspect >= 1 ? '100%' : 'auto') : '100%',
              height: videoAspect ? (videoAspect >= 1 ? 'auto' : '100%') : '100%',
              aspectRatio: videoAspect ? `${videoAspect}` : '16/9',
              maxHeight: '100%',
              maxWidth: '100%'
            }}
            src={videoUrl}
            onTimeUpdate={handleTimeUpdate}
            onLoadedMetadata={handleLoadedMetadata}
            onDurationChange={handleLoadedMetadata}
            onCanPlay={handleLoadedMetadata}
            onEnded={() => { if(!isLooping) setIsPlaying(false) }}
            playsInline
          />
        </div>

        {/* Middle Section: Controls */}
        <div className="flex items-center justify-center gap-2 py-2 mb-10 shrink-0">
          <button onClick={toggleMute} className="text-white hover:bg-white/10 w-9 h-9 flex items-center justify-center rounded-xl transition focus:outline-none cursor-pointer">
            {isMuted ? <VolumeX size={18} /> : <Volume2 size={18} />}
          </button>
          
          <span className="text-white text-[13px] font-bold tracking-[0.05em] w-[64px] text-center" style={{ fontFamily: "'Poppins', sans-serif" }}>{currentTime}</span>
          
          <div className="flex items-center gap-2 mx-1">
            <button onClick={skipBackward} className="text-white hover:bg-white/10 w-9 h-9 flex items-center justify-center rounded-xl transition focus:outline-none cursor-pointer">
              <SkipBack size={16} fill="white" />
            </button>
            
            <button onClick={togglePlay} className="w-9 h-9 bg-white rounded-xl flex items-center justify-center shadow-[0_0_15px_rgba(255,255,255,0.15)] cursor-pointer mx-1">
              {isPlaying ? (
                <Pause size={18} fill="black" stroke="black" />
              ) : (
                <Play size={18} fill="black" stroke="black" className="ml-1" />
              )}
            </button>
            
            <button onClick={skipForward} className="text-white hover:bg-white/10 w-9 h-9 flex items-center justify-center rounded-xl transition focus:outline-none cursor-pointer">
              <SkipForward size={16} fill="white" />
            </button>
          </div>

          <span className="text-gray-500 text-[13px] font-bold tracking-[0.05em] w-[64px] text-center" style={{ fontFamily: "'Poppins', sans-serif" }}>{durationStr}</span>
          
          <button onClick={toggleFullScreen} className="text-white hover:bg-white/10 w-9 h-9 flex items-center justify-center rounded-xl transition focus:outline-none cursor-pointer" title="Fullscreen">
            <Maximize size={18} />
          </button>
          
          <button onClick={toggleLoop} className={`w-9 h-9 rounded-xl flex items-center justify-center transition focus:outline-none cursor-pointer hover:bg-white/10`} title="Repeat/Loop">
            <Repeat size={14} className={isLooping ? "text-blue-400" : "text-gray-300"} />
          </button>

          <button onClick={downloadVideo} className="w-9 h-9 rounded-xl flex items-center justify-center transition focus:outline-none cursor-pointer hover:bg-white/10" title="Download Video">
            <Download size={14} className="text-gray-300" />
          </button>
        </div>

        {/* Bottom Section: Timeline */}
        <div className="w-full shrink-0 h-32 relative select-none">
          <div 
            ref={timelineRef}
            className={`absolute inset-0 bg-[#0a0a0a] border-t border-gray-800 pt-1 ${isDragging ? 'cursor-grabbing' : 'cursor-pointer'}`}
            onMouseDown={handleTimelineMouseDown}
          >
            
            {/* Ticks and time labels */}
            <div className="absolute top-0 left-2 right-2 h-8 relative">
              {tickIndices.map((second) => {
                const pct = (second / totalSeconds) * 100;
                return (
                  <div 
                    key={second} 
                    className="absolute top-0 bottom-0 pointer-events-none"
                    style={{ left: `${pct}%` }}
                  >
                    <div className="w-px h-2.5 bg-gray-600/70 -translate-x-1/2" />
                    <span 
                      className={`text-[11px] text-gray-400 absolute top-3 select-none font-medium ${
                        second === 0 ? "left-0" : second === totalSeconds ? "right-0" : "left-1/2 -translate-x-1/2"
                      }`}
                      style={{ fontFamily: "'Poppins', sans-serif" }}
                    >
                      {second.toString().padStart(2, '0')}
                    </span>
                  </div>
                );
              })}

              {/* Intermediate half-second ticks for shorter videos */}
              {totalSeconds <= 8 && Array.from({ length: totalSeconds }).map((_, i) => (
                <div 
                  key={`half-${i}`} 
                  className="absolute top-0 h-1.5 w-px bg-gray-800 pointer-events-none -translate-x-1/2"
                  style={{ left: `${((i + 0.5) / totalSeconds) * 100}%` }}
                />
              ))}
            </div>

            {/* Video Frames Track */}
            <div className="absolute top-10 left-2 right-2 h-[60px] bg-white/5 rounded-md border border-white p-[1px] flex overflow-hidden shadow-[0_0_15px_rgba(255,255,255,0.1)]">
               {Array.from({ length: frameCount }).map((_, i) => (
                 <div key={i} className="flex-1 h-full bg-[#111] border-r border-black/50 last:border-r-0 relative pointer-events-none">
                    <video 
                      src={`${videoUrl}#t=${((i + 0.5) * effectiveDuration) / frameCount}`} 
                      className="w-full h-full object-cover opacity-90" 
                      preload="metadata" 
                    />
                 </div>
               ))}
            </div>

            {/* Playhead */}
            <div 
              className={`absolute top-0 bottom-0 w-px bg-white z-20 ${isDragging ? 'cursor-grabbing' : 'cursor-grab'}`} 
              style={{ 
                left: `calc(0.5rem + (${progress} * (100% - 1rem)) / 100)`
              }}
            >
               <div className={`absolute top-0 left-1/2 -translate-x-1/2 w-3 h-5 bg-white rounded-b-md transition-transform hover:scale-110 ${isDragging ? 'cursor-grabbing' : 'cursor-grab'}`}></div>
            </div>
            
          </div>
        </div>
      </div>
      
      {/* Floating Action Buttons: Prompts + Wrench */}
      <div className="absolute top-6 right-6 z-40 flex items-center gap-2">
        {/* Prompts Button */}
        {prompts && prompts.length > 0 && (
          <button 
            onClick={() => {
              setIsPromptsModalOpen(true);
              if (isFixPanelOpen) setIsFixPanelOpen(false);
            }}
            className="flex items-center gap-2 bg-gray-900/90 hover:bg-gray-800 hover:border-purple-500/50 px-3.5 py-2.5 rounded-xl border border-gray-700 text-purple-300 transition-all shadow-[0_0_15px_rgba(168,85,247,0.15)] hover:shadow-[0_0_20px_rgba(168,85,247,0.3)] hover:scale-105 cursor-pointer backdrop-blur-md font-medium text-xs"
            title="View Generated Prompts & Visual Assets"
          >
            <Sparkles size={15} className="text-purple-400" />
            <span>Prompts & Assets ({prompts.length})</span>
          </button>
        )}

        {/* Floating Wrench Button (Visible when panel is closed) */}
        {!isFixPanelOpen && (
          <button 
            onClick={() => {
              setIsFixPanelOpen(true);
              setIsPromptsModalOpen(false);
            }}
            className="bg-gray-900/90 hover:bg-gray-800 p-2.5 rounded-xl border border-gray-700 text-blue-400 transition-all shadow-[0_0_15px_rgba(59,130,246,0.2)] hover:scale-105 cursor-pointer backdrop-blur-md"
            title="Open Fix Panel"
          >
            <Wrench size={18} />
          </button>
        )}
      </div>

      {/* Right Column: Editing Tools */}
      <div 
        className={`shrink-0 flex flex-col h-full transition-all duration-[700ms] ease-[cubic-bezier(0.16,1,0.3,1)] ${isFixPanelOpen ? 'w-80 pr-2 pb-2 opacity-100' : 'w-0 opacity-0 overflow-hidden'}`}
      >
        
        {/* Fix Panel */}
        <div className={`bg-gray-900/80 rounded-xl p-5 border border-gray-800 flex flex-col h-full origin-top-right transition-all duration-[700ms] ease-[cubic-bezier(0.16,1,0.3,1)] min-w-[312px] ${isFixPanelOpen ? 'scale-y-100 opacity-100' : 'scale-y-0 opacity-0'}`}>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2 text-blue-400">
              <div className="bg-blue-600/20 p-1.5 rounded-lg">
                <Wrench size={18} />
              </div>
              <h3 className="font-semibold text-[15px] text-white">Fix a Part of the Video</h3>
            </div>
            <button onClick={() => setIsFixPanelOpen(false)} className="text-gray-400 hover:text-white p-1 rounded-md hover:bg-gray-800 transition">
              <X size={20} />
            </button>
          </div>
          <p className="text-xs text-gray-400 mb-5 leading-relaxed">
            Select a time range on the timeline and describe what you want to fix. We'll generate a new clip for that section and automatically merge it.
          </p>
          
          <div className="bg-gray-950 rounded-lg p-3 border border-gray-800 mb-4 flex flex-col">
            <div className="flex justify-between items-center mb-2">
              <label className="text-[10px] text-gray-500 uppercase tracking-wider block">Selected Video Part</label>
              <button className="text-xs text-gray-400 hover:text-white px-2 py-1 rounded bg-gray-800/50">Clear</button>
            </div>
            
            <div className="relative mb-2">
              <select 
                value={selectedPart}
                onChange={(e) => setSelectedPart(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg p-2 text-sm text-gray-200 appearance-none focus:outline-none focus:border-blue-500 cursor-pointer"
              >
                {parts.map(p => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
                <option value="custom">Custom Time Range...</option>
              </select>
              <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-gray-400 text-xs">
                ▼
              </div>
            </div>

            {selectedPart === 'custom' && (
              <div className="flex items-center gap-2 text-sm font-medium bg-gray-900/50 p-2 rounded-lg border border-gray-800/50 mt-1">
                <span className="text-xs text-gray-400 mr-1">From:</span>
                <input 
                  type="text" 
                  defaultValue="7.0" 
                  className="w-12 bg-gray-900 border border-gray-700 rounded px-1 py-0.5 text-center focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50" 
                />
                <span className="text-gray-500 text-xs">s</span>
                <span className="text-gray-600 mx-1 text-xs">to</span>
                <input 
                  type="text" 
                  defaultValue="10.0" 
                  className="w-12 bg-gray-900 border border-gray-700 rounded px-1 py-0.5 text-center focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50" 
                />
                <span className="text-gray-500 text-xs">s</span>
              </div>
            )}
          </div>

          <div className="mb-4 flex-1 flex flex-col">
            <label className="text-xs font-medium text-gray-300 mb-2 block">Describe the issue & how to fix it <span className="text-red-400">*</span></label>
            <textarea 
              className="w-full flex-1 bg-gray-950 border border-gray-800 rounded-lg p-3 text-sm text-gray-200 resize-none focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/50"
              placeholder="E.g., In this part, the model's hand direction is wrong. Please correct it so she is holding the map properly."
              defaultValue=""
            />
            <div className="text-right text-[10px] text-gray-500 mt-1">145/500</div>
          </div>

          <button className="w-full bg-blue-600 hover:bg-blue-500 text-white font-medium py-2.5 rounded-lg flex items-center justify-center gap-2 transition mt-auto shrink-0">
            <Sparkles size={16} />
            Fix Selected Part
          </button>
        </div>
      </div>

      {/* Prompts Modal Overlay */}
      {isPromptsModalOpen && (
        <div 
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 md:p-8 animate-in fade-in duration-200"
          onClick={() => setIsPromptsModalOpen(false)}
        >
          <div 
            className="relative w-full max-w-4xl max-h-[85vh] bg-[#0c0d12] border border-gray-800 rounded-2xl shadow-[0_10px_50px_rgba(0,0,0,0.85)] flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-[#10121a]/90 shrink-0">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
                  <Sparkles size={18} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white flex items-center gap-2">
                    Generated Prompts & Visual Assets
                    <span className="text-xs px-2.5 py-0.5 rounded-full bg-purple-500/15 text-purple-300 font-normal border border-purple-500/30">
                      {prompts.length} Shots
                    </span>
                    {projectImages?.total_images ? (
                      <span className="text-xs px-2.5 py-0.5 rounded-full bg-blue-500/15 text-blue-300 font-normal border border-blue-500/30">
                        {projectImages.total_images} Gemini Images
                      </span>
                    ) : null}
                  </h3>
                  <p className="text-xs text-gray-400">
                    Total Runtime: {effectiveDuration.toFixed(1)}s · Cinematic directives & conditioning reference images
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2.5">
                <button
                  onClick={handleCopyAll}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium cursor-pointer transition-all ${
                    copiedAll 
                      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400" 
                      : "border-gray-700 bg-gray-900/80 hover:bg-gray-800 text-gray-300 hover:text-white"
                  }`}
                  title="Copy all prompts to clipboard"
                >
                  {copiedAll ? <Check size={14} /> : <Copy size={14} />}
                  <span>{copiedAll ? "All Copied!" : "Copy All Prompts"}</span>
                </button>

                <button
                  onClick={() => setIsPromptsModalOpen(false)}
                  className="text-gray-400 hover:text-white p-1.5 rounded-lg hover:bg-gray-800 transition cursor-pointer"
                  title="Close (Esc)"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Modal Scrollable Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {/* Project Master Visual Anchors (Global Reusable Entities) */}
              {projectImages?.master_assets && Object.keys(projectImages.master_assets).length > 0 && (
                <div className="p-4 rounded-xl bg-gradient-to-r from-amber-500/10 to-purple-500/10 border border-amber-500/20 flex flex-col gap-3 mb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs font-semibold text-amber-300">
                      <Sparkles size={14} className="text-amber-400" />
                      <span>Project Master Visual Anchors (Gemini Generated)</span>
                    </div>
                    <span className="text-[11px] text-gray-400">
                      Locked entities reused across scenes for 100% visual consistency
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5">
                    {Object.entries(projectImages.master_assets).map(([assetId, path]) => {
                      const fullUrl = resolveImageUrl(path);
                      const isChar = assetId.toLowerCase().includes("char");
                      const roleLabel = isChar ? "CHARACTER" : "PRODUCT";
                      return (
                        <div
                          key={assetId}
                          onClick={() => setActiveLightboxImage({
                            url: fullUrl,
                            label: assetId,
                            role: roleLabel,
                            reused: false,
                          })}
                          className="group relative aspect-video rounded-lg overflow-hidden bg-black/60 border border-amber-500/30 hover:border-amber-400 cursor-pointer transition-all"
                        >
                          <img
                            src={fullUrl}
                            alt={assetId}
                            className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                          />
                          <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent opacity-75 group-hover:opacity-90" />
                          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/30 text-white text-[10px] font-medium gap-1">
                            <ZoomIn size={12} /> Inspect
                          </div>
                          <div className="absolute bottom-1.5 left-1.5 right-1.5 flex items-center justify-between text-[9px]">
                            <span className="px-1.5 py-0.5 rounded bg-amber-500/30 text-amber-200 border border-amber-500/30 font-semibold truncate">
                              {roleLabel}
                            </span>
                            <span className="text-gray-300 truncate max-w-[80px]">
                              {assetId}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {prompts.map((prompt, idx) => {
                let fullPromptText = prompt.prompt_text;
                if (prompt.negative_constraints) {
                  fullPromptText += `\n\nNegative: ${prompt.negative_constraints}`;
                }
                if (prompt.continuity_requirements && prompt.continuity_requirements.length > 0) {
                  fullPromptText += `\n\nContinuity: ${prompt.continuity_requirements.join(', ')}`;
                }

                const isCopied = copiedIndex === idx;

                // Match shot images
                const shotImages: ShotImageAsset[] = projectImages?.shots?.find(
                  (s) => s.shot_id === prompt.shot_id || (s.sequence_number !== undefined && s.sequence_number === (prompt.sequence_number || idx + 1))
                )?.images || [];

                return (
                  <div
                    key={prompt.prompt_id || idx}
                    className="p-5 rounded-xl bg-[#12141c]/90 border border-gray-800/80 flex flex-col gap-3 relative overflow-hidden hover:border-gray-700 transition"
                  >
                    <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-purple-500 to-blue-500" />

                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold px-2.5 py-1 rounded-md bg-white/5 text-gray-300 border border-white/5">
                          Shot {prompt.sequence_number || idx + 1}
                        </span>
                        <span className="text-xs text-gray-400">
                          {prompt.duration_seconds}s
                          {prompt.camera_parameters ? ` · ${prompt.camera_parameters}` : ""}
                        </span>
                      </div>

                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(fullPromptText);
                          setCopiedIndex(idx);
                          setTimeout(() => setCopiedIndex(null), 2000);
                        }}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs cursor-pointer transition-all ${
                          isCopied
                            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-400"
                            : "border-gray-800 bg-gray-900/60 hover:bg-gray-800 text-gray-400 hover:text-white"
                        }`}
                        title="Copy this shot prompt"
                      >
                        {isCopied ? <Check size={13} /> : <Copy size={13} />}
                        <span>{isCopied ? "Copied!" : "Copy"}</span>
                      </button>
                    </div>

                    <div className="bg-[#090a0f] rounded-lg p-3.5 border border-gray-800/60">
                      <p className="text-xs font-mono leading-relaxed text-gray-200 whitespace-pre-wrap selection:bg-purple-500/30">
                        {fullPromptText}
                      </p>
                    </div>

                    {/* Shot Reference Images (Gemini Generated) */}
                    {shotImages.length > 0 && (
                      <div className="pt-2 border-t border-gray-800/60 flex flex-col gap-2">
                        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-300">
                          <ImageIcon size={13} className="text-purple-400" />
                          <span>Veo Condition Reference Images ({shotImages.length}):</span>
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5">
                          {shotImages.map((img, imgIdx) => {
                            const fullUrl = resolveImageUrl(img.path || img.url);
                            return (
                              <div
                                key={img.asset_id || imgIdx}
                                onClick={() => setActiveLightboxImage({
                                  url: fullUrl,
                                  label: img.asset_id,
                                  role: img.role,
                                  reused: img.reused,
                                })}
                                className="group relative aspect-video rounded-lg overflow-hidden bg-black/50 border border-gray-800 hover:border-purple-500/60 cursor-pointer transition-all"
                              >
                                <img
                                  src={fullUrl}
                                  alt={img.asset_id}
                                  className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                                  loading="lazy"
                                />
                                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent opacity-70 group-hover:opacity-90" />
                                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/30 text-white text-[10px] font-medium gap-1">
                                  <ZoomIn size={12} /> Inspect
                                </div>
                                <div className="absolute bottom-1.5 left-1.5 right-1.5 flex items-center justify-between text-[9px]">
                                  <span className={`px-1.5 py-0.5 rounded border font-semibold ${getRoleBadgeStyle(img.role)}`}>
                                    {img.role}
                                  </span>
                                  {img.reused && (
                                    <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                      Master
                                    </span>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {/* Negative / Continuity / Tags */}
                    {(prompt.style_modifiers || prompt.motion_parameters) && (
                      <div className="flex flex-wrap gap-2 pt-1">
                        {prompt.style_modifiers && (
                          <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-purple-500/10 text-purple-300 border border-purple-500/20">
                            Style: {prompt.style_modifiers}
                          </span>
                        )}
                        {prompt.motion_parameters && (
                          <span className="text-[11px] px-2.5 py-0.5 rounded-full bg-blue-500/10 text-blue-300 border border-blue-500/20">
                            Motion: {prompt.motion_parameters}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Lightbox Modal */}
      {activeLightboxImage && (
        <div
          className="fixed inset-0 z-[60] bg-black/90 backdrop-blur-xl flex items-center justify-center p-4 animate-in fade-in duration-200"
          onClick={() => setActiveLightboxImage(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] bg-[#0d0e15] border border-gray-800 rounded-2xl overflow-hidden flex flex-col shadow-[0_20px_60px_rgba(0,0,0,0.9)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800 bg-[#12141e]/90">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${getRoleBadgeStyle(activeLightboxImage.role)}`}>
                  {activeLightboxImage.role}
                </span>
                <span className="text-xs font-semibold text-white">
                  {activeLightboxImage.label}
                </span>
                {activeLightboxImage.reused && (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                    Master Anchor
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <a
                  href={activeLightboxImage.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 text-xs text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-gray-800 transition"
                >
                  <ExternalLink size={13} /> High-Res
                </a>
                <button
                  onClick={() => setActiveLightboxImage(null)}
                  className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-800 transition cursor-pointer"
                >
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="flex-1 bg-black flex items-center justify-center p-2 overflow-hidden">
              <img
                src={activeLightboxImage.url}
                alt={activeLightboxImage.label}
                className="max-h-[75vh] w-auto object-contain rounded-lg shadow-lg"
              />
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
