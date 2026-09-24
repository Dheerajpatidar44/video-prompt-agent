<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { ApiClient } from '$lib/api/client';
  import { currentScenePlan } from '$lib/stores/project';
  import { Clapperboard, Clock, Video, Loader2 } from '@lucide/svelte';

  let isLoading = $state(true);
  let errorMessage = $state('');

  let threadId = $derived($page.params.threadId || '');

  onMount(async () => {
    if (!$currentScenePlan) {
      try {
        const response = await ApiClient.getScenePlan(threadId);
        currentScenePlan.set(response.scene_plan);
      } catch (error: any) {
        errorMessage = error.message || 'Failed to load scene plan.';
      } finally {
        isLoading = false;
      }
    } else {
      isLoading = false;
    }
  });

  function formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }
</script>

<div class="max-w-5xl mx-auto space-y-8 pb-12">
  <div class="flex items-center justify-between mb-8">
    <div>
      <h2 class="text-3xl font-bold tracking-tight mb-2">Master Scene Plan</h2>
      <p class="text-surface-400">
        Structured scene-by-scene and shot-by-shot breakdown before prompt generation.
      </p>
    </div>
    
    {#if $currentScenePlan}
      <div class="glass-card px-6 py-4 flex items-center gap-6">
        <div class="flex flex-col">
          <span class="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-1">Total Duration</span>
          <span class="text-2xl font-bold text-surface-50 flex items-center gap-2">
            <Clock size={20} class="text-brand-400" />
            {formatTime($currentScenePlan.total_duration)}
          </span>
        </div>
        <div class="h-10 w-px bg-surface-700"></div>
        <div class="flex flex-col">
          <span class="text-xs font-semibold text-surface-400 uppercase tracking-wider mb-1">Total Scenes</span>
          <span class="text-2xl font-bold text-surface-50 flex items-center gap-2">
            <Clapperboard size={20} class="text-accent-primary" />
            {$currentScenePlan.scenes.length}
          </span>
        </div>
      </div>
    {/if}
  </div>

  {#if isLoading}
    <div class="flex flex-col items-center justify-center py-20 text-surface-400 gap-4">
      <Loader2 size={32} class="animate-spin text-brand-500" />
      <p>Building scene plan...</p>
    </div>
  {:else if errorMessage}
    <div class="p-4 rounded-lg bg-red-500/10 border border-red-500/50 text-red-400 text-sm">
      {errorMessage}
    </div>
  {:else if $currentScenePlan}
    
    <div class="space-y-8">
      {#each $currentScenePlan.scenes as scene, index}
        <div class="glass-card overflow-hidden border-surface-700/50">
          <!-- Scene Header -->
          <div class="bg-surface-900/80 border-b border-surface-800 p-6 flex flex-col md:flex-row gap-6 justify-between items-start">
            <div class="flex-1">
              <div class="flex items-center gap-3 mb-2">
                <span class="px-2 py-1 rounded bg-brand-500/20 text-brand-400 text-xs font-bold font-mono">
                  SCENE {scene.scene_number}
                </span>
                <h3 class="text-xl font-bold text-surface-50">{scene.title}</h3>
              </div>
              <p class="text-surface-300 text-sm mb-4 leading-relaxed">{scene.purpose}</p>
              
              <div class="flex flex-wrap gap-4 text-xs">
                <div class="flex items-center gap-1.5 text-surface-400">
                  <span class="font-semibold text-surface-300">Location:</span> {scene.location}
                </div>
                <div class="flex items-center gap-1.5 text-surface-400">
                  <span class="font-semibold text-surface-300">Duration:</span> {scene.duration_seconds}s
                </div>
              </div>
            </div>
          </div>
          
          <!-- Shots List -->
          <div class="p-0 bg-surface-950/30">
            <div class="overflow-x-auto">
              <table class="w-full text-left text-sm whitespace-nowrap">
                <thead class="bg-surface-900/50 text-surface-400 border-b border-surface-800 text-xs uppercase tracking-wider">
                  <tr>
                    <th class="px-6 py-4 font-medium">Shot</th>
                    <th class="px-6 py-4 font-medium">Duration</th>
                    <th class="px-6 py-4 font-medium w-1/3">Action / Subject</th>
                    <th class="px-6 py-4 font-medium">Framing</th>
                    <th class="px-6 py-4 font-medium">Camera Motion</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-surface-800/50">
                  {#each scene.shots as shot}
                    <tr class="hover:bg-surface-800/20 transition-colors">
                      <td class="px-6 py-4">
                        <span class="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-surface-800 text-surface-200 font-mono text-xs">
                          <Video size={12} class="text-surface-400" />
                          {shot.shot_number}
                        </span>
                      </td>
                      <td class="px-6 py-4 text-surface-300 font-mono text-xs">
                        {shot.duration_seconds}s
                      </td>
                      <td class="px-6 py-4">
                        <p class="text-surface-200 truncate max-w-[300px]" title={shot.action}>
                          <span class="font-semibold text-brand-400 mr-2">{shot.subject}</span>
                          {shot.action}
                        </p>
                      </td>
                      <td class="px-6 py-4 text-surface-300">
                        {shot.framing}
                      </td>
                      <td class="px-6 py-4 text-surface-300">
                        {shot.camera_movement}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      {/each}
    </div>

    <div class="mt-8 flex justify-end">
      <a 
        href={`/project/${threadId}/prompts`}
        class="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium shadow-lg shadow-brand-500/20 transition-all duration-300"
      >
        View Generated Prompts
      </a>
    </div>
  {/if}
</div>
