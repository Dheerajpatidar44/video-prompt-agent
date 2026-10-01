"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { ResultsView } from "@/components/sections/ResultsView";
import { ApiClient } from "@/lib/api/client";
import { ArrowLeft } from "lucide-react";
import type { MasterScenePlan, PromptSet } from "@/lib/types";

export default function ProjectDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scenePlan, setScenePlan] = useState<MasterScenePlan | null>(null);
  const [prompts, setPrompts] = useState<PromptSet | null>(null);

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

        <main className="flex-1 overflow-y-auto p-6 md:p-8 lg:p-12 relative z-0">
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
                  onReset={() => router.push('/')} 
                />
              </motion.div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
