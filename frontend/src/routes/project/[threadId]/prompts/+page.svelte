<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { ApiClient } from '$lib/api/client';
  import { currentPromptSet } from '$lib/stores/project';
  import { Copy, Check, CheckCircle2, AlertTriangle, Loader2, Sparkles, Image as ImageIcon } from '@lucide/svelte';

  let isLoading = $state(true);
  let errorMessage = $state('');
  let copiedId: string | null = $state(null);

  let threadId = $derived($page.params.threadId || '');

  onMount(async () => {
    if (!$currentPromptSet) {
      try {
        const response = await ApiClient.getPrompts(threadId);
        currentPromptSet.set(response.prompt_set);
      } catch (error: any) {
        errorMessage = error.message || 'Failed to load prompts.';
      } finally {
        isLoading = false;
      }
    } else {
      isLoading = false;
    }
  });

  function copyToClipboard(text: string, id: string) {
    navigator.clipboard.writeText(text);
    copiedId = id;
    setTimeout(() => {
      if (copiedId === id) copiedId = null;
    }, 2000);
  }

  function getAspectRatioBadge(ratio: string) {
    return `<span class="px-2 py-1 rounded bg-surface-800 text-surface-200 text-xs font-mono font-bold border border-surface-700">${ratio}</span>`;
  }
</script>

<div class="max-w-6xl mx-auto space-y-8 pb-12">
  <div class="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-8">
    <div>
      <h2 class="text-3xl font-bold tracking-tight mb-2 flex items-center gap-3">
        Production Prompts
        <Sparkles size={24} class="text-accent-primary" />
      </h2>
      <p class="text-surface-400 max-w-2xl">
        Final, validated text prompts ready for AI video generators (Runway Gen-2, Pika, Sora, Kling).
      </p>
    </div>
    
    {#if $currentPromptSet}
      <div class="flex items-center gap-4">
        <div class="px-4 py-2 rounded-lg bg-surface-900 border border-surface-800 flex items-center gap-2">
          <ImageIcon size={16} class="text-surface-400" />
          <span class="text-sm font-medium text-surface-200">Ratio: {$currentPromptSet.aspect_ratio}</span>
        </div>
        {#if $currentPromptSet.validation_issues && $currentPromptSet.validation_issues.length === 0}
          <div class="px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-2">
            <CheckCircle2 size={16} class="text-emerald-400" />
            <span class="text-sm font-medium text-emerald-400">All Prompts Validated</span>
          </div>
        {/if}
      </div>
    {/if}
  </div>

  {#if isLoading}
    <div class="flex flex-col items-center justify-center py-20 text-surface-400 gap-4">
      <Loader2 size={32} class="animate-spin text-brand-500" />
      <p>Generating prompts...</p>
    </div>
  {:else if errorMessage}
    <div class="p-4 rounded-lg bg-red-500/10 border border-red-500/50 text-red-400 text-sm">
      {errorMessage}
    </div>
  {:else if $currentPromptSet}
    
    {#if $currentPromptSet.validation_issues && $currentPromptSet.validation_issues.length > 0}
      <div class="p-4 rounded-xl bg-orange-500/10 border border-orange-500/30 mb-8">
        <h4 class="text-orange-400 font-bold flex items-center gap-2 mb-2">
          <AlertTriangle size={18} />
          Validation Warnings
        </h4>
        <ul class="list-disc list-inside text-sm text-orange-300 space-y-1">
          {#each $currentPromptSet.validation_issues as issue}
            <li>{issue}</li>
          {/each}
        </ul>
      </div>
    {/if}

    <div class="space-y-6">
      {#each $currentPromptSet.prompts as prompt}
        <div class="glass-card overflow-hidden group">
          <div class="px-6 py-3 border-b border-surface-800 bg-surface-900/50 flex justify-between items-center">
            <div class="flex items-center gap-3">
              <span class="px-2.5 py-1 rounded-md bg-surface-950 text-surface-200 font-mono text-xs font-bold border border-surface-800">
                SHOT {prompt.shot_id.split('_').pop()}
              </span>
              <span class="text-sm font-medium text-surface-400">
                Duration: {prompt.duration_seconds}s
              </span>
            </div>
            
            <button 
            onclick={() => copyToClipboard(prompt.prompt_text, prompt.prompt_id)}
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-500/10 hover:bg-brand-500/20 text-brand-400 text-xs font-semibold transition-colors border border-brand-500/20"
            >
              {#if copiedId === prompt.prompt_id}
                <Check size={14} /> Copied!
              {:else}
                <Copy size={14} /> Copy Prompt
              {/if}
            </button>
          </div>
          
          <div class="p-6 bg-surface-950/40 relative">
            <p class="text-lg leading-relaxed text-surface-100 font-serif">
              {prompt.prompt_text}
            </p>
            
            {#if prompt.negative_constraints}
              <div class="mt-4 pt-4 border-t border-surface-800/50">
                <span class="text-xs font-bold text-red-400/80 uppercase tracking-wider block mb-1">Negative Constraints</span>
                <p class="text-sm text-surface-400 italic">
                  --no {prompt.negative_constraints}
                </p>
              </div>
            {/if}
          </div>
          
          <!-- Parameters Breakdown (Expandable or just grid) -->
          <div class="px-6 py-4 bg-surface-900/80 border-t border-surface-800 grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div>
              <span class="block text-surface-500 font-semibold uppercase mb-1">Camera</span>
              <span class="text-surface-300 line-clamp-2" title={prompt.camera_parameters}>{prompt.camera_parameters}</span>
            </div>
            <div>
              <span class="block text-surface-500 font-semibold uppercase mb-1">Lighting</span>
              <span class="text-surface-300 line-clamp-2" title={prompt.lighting_parameters}>{prompt.lighting_parameters}</span>
            </div>
            <div>
              <span class="block text-surface-500 font-semibold uppercase mb-1">Motion</span>
              <span class="text-surface-300 line-clamp-2" title={prompt.motion_parameters}>{prompt.motion_parameters}</span>
            </div>
            <div>
              <span class="block text-surface-500 font-semibold uppercase mb-1">Style</span>
              <span class="text-surface-300 line-clamp-2" title={prompt.style_modifiers}>{prompt.style_modifiers}</span>
            </div>
          </div>
        </div>
      {/each}
    </div>

  {/if}
</div>
