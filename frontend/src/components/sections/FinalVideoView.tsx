import React, { useState, useRef, useEffect } from "react";
import { Play, Pause, SkipBack, SkipForward, Volume2, VolumeX, Maximize, Repeat, Download, Wrench, Sparkles, X } from "lucide-react";

import type { GeneratedPrompt } from "@/lib/types";

export function FinalVideoView({ 
  videoUrl, 
  prompts = [], 
  totalDuration = 12 
}: { 
  videoUrl: string; 
  prompts?: GeneratedPrompt[]; 
  totalDuration?: number; 
}) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [isLooping, setIsLooping] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrentTime] = useState("00:00:00");
  const [durationStr, setDurationStr] = useState("00:00:12");
  const animationRef = useRef<number>(0);
  const [isDragging, setIsDragging] = useState(false);
  const timelineRef = useRef<HTMLDivElement>(null);
  const [selectedPart, setSelectedPart] = useState("part3");
  const [isFixPanelOpen, setIsFixPanelOpen] = useState(false);
  const [videoAspect, setVideoAspect] = useState<number | null>(null);

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

  const formatTime = (seconds: number) => {
    if (isNaN(seconds)) return "00:00:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    const cs = Math.floor((seconds % 1) * 100);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}:${cs.toString().padStart(2, '0')}`;
  };

  const updateTimeLoop = () => {
    if (videoRef.current) {
      const current = videoRef.current.currentTime;
      const dur = videoRef.current.duration || totalDuration;
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
      const dur = videoRef.current.duration || totalDuration;
      setProgress((current / dur) * 100);
      setCurrentTime(formatTime(current));
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDurationStr(formatTime(videoRef.current.duration));
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
      const newTime = percentage * (videoRef.current.duration || totalDuration);
      
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
            <div className="absolute top-0 left-0 right-0 h-8 flex justify-between px-2">
               {Array.from({length: 11}).map((_, i) => (
                 <div key={i} className="relative h-full border-l border-gray-700/50 flex-1 last:border-r">
                   <span className="text-[11px] text-gray-500 absolute top-2 -translate-x-1/2" style={{ fontFamily: "'Poppins', sans-serif" }}>
                     {i.toString().padStart(2, '0')}
                   </span>
                 </div>
               ))}
            </div>

            {/* Video Frames Track */}
            <div className="absolute top-10 left-2 right-2 h-[60px] bg-white/5 rounded-md border border-white p-[1px] flex overflow-hidden shadow-[0_0_15px_rgba(255,255,255,0.1)]">
               {Array.from({ length: 10 }).map((_, i) => (
                 <div key={i} className="flex-1 h-full bg-[#111] border-r border-black/50 last:border-r-0 relative pointer-events-none">
                    <video src={`${videoUrl}#t=${((i + 0.5) * (totalDuration || 12)) / 10}`} className="w-full h-full object-cover opacity-90" preload="metadata" />
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
      
      {/* Floating Wrench Button (Visible when panel is closed) */}
      {!isFixPanelOpen && (
        <button 
          onClick={() => setIsFixPanelOpen(true)}
          className="absolute top-6 right-6 z-50 bg-gray-900 hover:bg-gray-800 p-2.5 rounded-lg border border-gray-700 text-blue-400 transition-all shadow-[0_0_15px_rgba(59,130,246,0.2)] hover:scale-105"
          title="Open Fix Panel"
        >
          <Wrench size={20} />
        </button>
      )}

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
                {parts.length > 0 ? parts.map(p => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                )) : (
                  <>
                    <option value="part1">Part 1 (0.0s - 3.0s)</option>
                    <option value="part2">Part 2 (3.0s - 7.0s)</option>
                    <option value="part3">Part 3 (7.0s - 10.0s)</option>
                    <option value="part4">Part 4 (10.0s - 12.0s)</option>
                  </>
                )}
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

    </div>
  );
}
