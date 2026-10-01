"use client";

import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { ApiClient } from "@/lib/api/client";
import Swal from 'sweetalert2';
import { Calendar, Trash2, ArrowRight } from "lucide-react";
import Link from "next/link";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProjects();
  }, []);

  const fetchProjects = async () => {
    try {
      const data = await ApiClient.getProjects();
      setProjects(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const deleteProject = async (id: string, title: string) => {
    const result = await Swal.fire({
      title: 'Are you sure?',
      text: `Do you really want to delete "${title}"? This action cannot be undone.`,
      icon: 'warning',
      background: '#14161b',
      color: '#f0f2f5',
      showCancelButton: true,
      confirmButtonColor: '#ff3366',
      cancelButtonColor: '#3b82f6',
      confirmButtonText: 'Yes, delete it!',
      customClass: {
        popup: 'border border-white/10 rounded-xl',
      }
    });

    if (result.isConfirmed) {
      try {
        await ApiClient.deleteProject(id);
        setProjects((prev) => prev.filter((p) => p.id !== id));
        
        Swal.fire({
          title: 'Deleted!',
          text: 'Your project has been deleted.',
          icon: 'success',
          background: '#14161b',
          color: '#f0f2f5',
          confirmButtonColor: '#3b82f6',
          customClass: {
            popup: 'border border-white/10 rounded-xl',
          }
        });
      } catch (err) {
        console.error(err);
        Swal.fire({
          title: 'Error!',
          text: 'Something went wrong while deleting.',
          icon: 'error',
          background: '#14161b',
          color: '#f0f2f5',
          confirmButtonColor: '#3b82f6',
          customClass: {
            popup: 'border border-white/10 rounded-xl',
          }
        });
      }
    }
  };

  return (
    <div className="flex h-screen bg-[#050505] text-white overflow-hidden font-sans">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />

        <main className="flex-1 overflow-y-auto p-6 md:p-8 lg:p-12 relative z-0">
          <div className="max-w-7xl mx-auto space-y-8">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">Your Projects</h1>
              <p className="text-gray-400 mt-2">Manage your AI video generations.</p>
            </div>

            {loading ? (
              <div className="flex justify-center p-20">
                <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-[#ff3366]"></div>
              </div>
            ) : projects.length === 0 ? (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="w-full max-w-2xl mx-auto mt-8 flex flex-col items-center justify-center text-center p-12 md:p-16 border border-white/5 rounded-3xl bg-[#ffffff03] relative overflow-hidden"
              >
                {/* Background glow */}
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-48 h-48 bg-[#ff3366]/10 rounded-full blur-[80px] pointer-events-none"></div>

                <div className="w-16 h-16 bg-gradient-to-br from-[#ff3366]/20 to-[#ff3366]/5 border border-[#ff3366]/30 rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-[#ff3366]/10 text-[#ff3366] relative z-10">
                  <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 5v14" /><path d="M5 12h14" /></svg>
                </div>

                <h2 className="text-2xl md:text-3xl font-semibold mb-3 tracking-tight text-white relative z-10">No projects yet</h2>
                <p className="text-gray-400 mb-10 max-w-md mx-auto text-sm md:text-base leading-relaxed relative z-10">
                  You haven't generated any AI videos yet. Create your first project to bring your scripts to life.
                </p>

                <Link
                  href="/"
                  className="group relative inline-flex items-center justify-center gap-3 bg-white text-black h-12 px-8 rounded-full font-semibold overflow-hidden transition-all duration-300 hover:scale-105 active:scale-95 hover:shadow-[0_0_30px_rgba(255,255,255,0.3)] z-10"
                >
                  <span className="relative z-10 text-[15px]">Create New Project</span>
                  <ArrowRight size={18} className="relative z-10 group-hover:translate-x-1 transition-transform" />
                  <div className="absolute inset-0 bg-gray-100 opacity-0 group-hover:opacity-100 transition-opacity"></div>
                </Link>
              </motion.div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {projects.map((project, idx) => {
                  const isCompleted = project.status === 'COMPLETED';

                  const cardContent = (
                    <motion.div
                      key={project.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: idx * 0.05 }}
                      onClick={() => {
                        window.location.href = `/projects/${project.id}`;
                      }}
                      className={`glass-panel group relative overflow-hidden flex flex-col transition-all duration-300 hover:shadow-[0_0_20px_rgba(59,130,246,0.15)] hover:border-[#3b82f6]/30 cursor-pointer`}
                    >
                      <div className="h-44 bg-gradient-to-br from-white/5 to-transparent relative flex items-center justify-center overflow-hidden">
                        {project.thumbnail_url ? (
                          <img src={project.thumbnail_url} className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" alt="Thumbnail" />
                        ) : (
                          <div className="absolute inset-0 bg-gradient-to-br from-[#3b82f6]/20 via-[#10141f] to-black opacity-80 flex flex-col items-center justify-center">
                            <div className="w-12 h-12 rounded-full border border-white/10 flex items-center justify-center mb-2 bg-black/50 shadow-[0_0_15px_rgba(59,130,246,0.2)]">
                              <span className="text-[#3b82f6] text-xl font-bold">{project.title.charAt(0).toUpperCase()}</span>
                            </div>
                            <span className="text-gray-400/80 text-xs font-medium tracking-wider">NO THUMBNAIL</span>
                          </div>
                        )}

                        <div className="absolute top-3 right-3 bg-black/70 backdrop-blur-md px-3 py-1.5 rounded-md text-[10px] font-bold uppercase tracking-wider border border-white/10 flex items-center gap-1 shadow-lg">
                          {project.tool}
                        </div>
                      </div>

                      <div className="p-5 flex flex-col flex-1 bg-gradient-to-b from-transparent to-black/40">
                        <h3 className="text-lg font-medium line-clamp-1 mb-2 group-hover:text-white transition-colors">{project.title}</h3>

                        <div className="flex items-center gap-2 text-xs text-gray-500 mb-4 mt-auto">
                          <Calendar size={13} className="text-gray-600" />
                          {new Date(project.created_at).toLocaleDateString(undefined, {
                            year: 'numeric',
                            month: 'short',
                            day: 'numeric'
                          })}
                        </div>

                        <div className="flex items-center justify-between mt-2 pt-4 border-t border-white/5">
                          <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1.5 rounded-full ${isCompleted ? 'bg-[#00ff9d]/10 text-[#00ff9d] border border-[#00ff9d]/20' :
                              project.status === 'ERROR' ? 'bg-[#ff3366]/10 text-[#ff3366] border border-[#ff3366]/20' :
                                'bg-[#33a1ff]/10 text-[#33a1ff] border border-[#33a1ff]/20'
                            }`}>
                            {project.status}
                          </span>

                          <div className="flex gap-2">
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                deleteProject(project.id, project.title);
                              }}
                              className="p-2 rounded-lg hover:bg-[#ff3366]/10 text-gray-500 hover:text-[#ff3366] transition-all duration-300 z-10"
                              title="Delete project"
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  );

                  return cardContent;
                })}
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
