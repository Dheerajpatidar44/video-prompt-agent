<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { ApiClient } from '$lib/api/client';
  import { currentSpecification } from '$lib/stores/project';
  import { FileText, Camera, Lightbulb, Music, Maximize, AlertTriangle, Loader2 } from '@lucide/svelte';

  let isLoading = $state(true);
  let errorMessage = $state('');

  let threadId = $derived($page.params.threadId || '');

  onMount(async () => {
    if (!$currentSpecification) {
      try {
        const response = await ApiClient.getSpecification(threadId);
        currentSpecification.set(response.video_specification);
      } catch (error: any) {
        errorMessage = error.message || 'Failed to load specification.';
      } finally {
        isLoading = false;
      }
    } else {
      isLoading = false;
    }
  });

  function getSourceColor(source: string) {
    switch (source) {
      case 'USER': return 'text-brand-400 bg-brand-500/10 border-brand-500/20';
      case 'SCRIPT': return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
      case 'INFERRED': return 'text-orange-400 bg-orange-500/10 border-orange-500/20';
      case 'SYSTEM_DEFAULT': return 'text-surface-400 bg-surface-700/50 border-surface-600';
      default: return 'text-surface-300 bg-surface-800 border-surface-700';
    }
  }
</script>

<div class="max-w-5xl mx-auto space-y-8 pb-12">
  <div class="mb-8">
    <h2 class="text-3xl font-bold tracking-tight mb-2">Continuity Bible & Specification</h2>
    <p class="text-surface-400">
      The single source of truth for the project. Every parameter here will be strictly enforced during scene planning and prompt generation.
    </p>
  </div>

  {#if isLoading}
    <div class="flex flex-col items-center justify-center py-20 text-surface-400 gap-4">
      <Loader2 size={32} class="animate-spin text-brand-500" />
      <p>Building specification...</p>
    </div>
  {:else if errorMessage}
    <div class="p-4 rounded-lg bg-red-500/10 border border-red-500/50 text-red-400 text-sm">
      {errorMessage}
    </div>
  {:else if $currentSpecification}
    
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- Camera Settings -->
      <div class="glass-card p-6">
        <h3 class="text-lg font-semibold flex items-center gap-2 text-surface-50 border-b border-surface-700 pb-3 mb-4">
          <Camera size={18} class="text-brand-400" />
          Camera & Framing
        </h3>
        
        <div class="space-y-4">
          {#each Object.entries($currentSpecification.camera) as [key, data]: [string, any]}
            {#if data && typeof data === 'object' && 'value' in data}
              <div class="flex justify-between items-start border-b border-surface-800/50 pb-3 last:border-0 last:pb-0">
                <span class="text-surface-300 text-sm capitalize">{key.replace(/_/g, ' ')}</span>
                <div class="flex flex-col items-end gap-1">
                  <span class="font-medium text-surface-100 text-sm">{(data as any).value}</span>
                  <span class="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded border {getSourceColor((data as any).source)}">
                    {(data as any).source}
                  </span>
                </div>
              </div>
            {/if}
          {/each}
        </div>
      </div>

      <!-- Lighting & Color -->
      <div class="glass-card p-6">
        <h3 class="text-lg font-semibold flex items-center gap-2 text-surface-50 border-b border-surface-700 pb-3 mb-4">
          <Lightbulb size={18} class="text-yellow-400" />
          Lighting & Aesthetics
        </h3>
        
        <div class="space-y-4">
          {#each Object.entries($currentSpecification.lighting) as [key, data]: [string, any]}
            {#if data && typeof data === 'object' && 'value' in data}
              <div class="flex justify-between items-start border-b border-surface-800/50 pb-3 last:border-0 last:pb-0">
                <span class="text-surface-300 text-sm capitalize">{key.replace(/_/g, ' ')}</span>
                <div class="flex flex-col items-end gap-1">
                  <span class="font-medium text-surface-100 text-sm">{(data as any).value}</span>
                  <span class="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded border {getSourceColor((data as any).source)}">
                    {(data as any).source}
                  </span>
                </div>
              </div>
            {/if}
          {/each}
        </div>
      </div>

      <!-- Output Requirements -->
      <div class="glass-card p-6">
        <h3 class="text-lg font-semibold flex items-center gap-2 text-surface-50 border-b border-surface-700 pb-3 mb-4">
          <Maximize size={18} class="text-accent-secondary" />
          Output Profile
        </h3>
        
        <div class="space-y-4">
          {#each Object.entries($currentSpecification.output_requirements) as [key, data]: [string, any]}
            {#if data && typeof data === 'object' && 'value' in data}
              <div class="flex justify-between items-start border-b border-surface-800/50 pb-3 last:border-0 last:pb-0">
                <span class="text-surface-300 text-sm capitalize">{key.replace(/_/g, ' ')}</span>
                <div class="flex flex-col items-end gap-1">
                  <span class="font-medium text-surface-100 text-sm">{(data as any).value}</span>
                </div>
              </div>
            {/if}
          {/each}
        </div>
      </div>

      <!-- Continuity Elements -->
      <div class="glass-card p-6">
        <h3 class="text-lg font-semibold flex items-center gap-2 text-surface-50 border-b border-surface-700 pb-3 mb-4">
          <FileText size={18} class="text-emerald-400" />
          Continuity Dictionary
        </h3>
        
        <div class="space-y-4 max-h-[300px] overflow-y-auto pr-2">
          {#each Object.entries($currentSpecification.continuity_bible) as [key, value]}
            <div class="bg-surface-900/50 rounded-lg p-3 border border-surface-800">
              <span class="block text-xs font-bold text-surface-400 uppercase mb-1">{key}</span>
              <p class="text-sm text-surface-200">{value}</p>
            </div>
          {/each}
        </div>
      </div>

      {#if $currentSpecification.unresolved_items && $currentSpecification.unresolved_items.length > 0}
        <div class="md:col-span-2 glass-card p-6 border-orange-500/30">
          <h3 class="text-lg font-semibold flex items-center gap-2 text-orange-400 border-b border-surface-700 pb-3 mb-4">
            <AlertTriangle size={18} />
            Unresolved Parameters
          </h3>
          <p class="text-sm text-surface-400 mb-4">
            The following parameters were left unresolved or skipped. System defaults will be applied where necessary.
          </p>
          <div class="flex flex-wrap gap-2">
            {#each $currentSpecification.unresolved_items as item}
              <span class="px-3 py-1 bg-orange-500/10 border border-orange-500/20 text-orange-400 rounded-full text-sm font-medium">
                {item}
              </span>
            {/each}
          </div>
        </div>
      {/if}

    </div>

    <div class="mt-8 flex justify-end">
      <a 
        href={`/project/${threadId}/scenes`}
        class="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium shadow-lg shadow-brand-500/20 transition-all duration-300"
      >
        View Scene Plan
      </a>
    </div>
  {/if}
</div>
