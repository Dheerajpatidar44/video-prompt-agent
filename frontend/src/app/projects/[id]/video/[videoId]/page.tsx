"use client";

import React from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { FinalVideoView } from "@/components/sections/FinalVideoView";

export default function VideoEditorPage() {
  return (
    <div className="flex h-screen bg-[#050505] text-white overflow-hidden font-sans">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />
        <main className="flex-1 overflow-hidden p-0 flex flex-col relative z-0">
          <FinalVideoView />
        </main>
      </div>
    </div>
  );
}
