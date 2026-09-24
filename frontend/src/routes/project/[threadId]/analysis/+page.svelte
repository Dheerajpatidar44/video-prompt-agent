<script lang="ts">
  import { Users, MapPin, Package, Target, FileText, CheckCircle2 } from '@lucide/svelte';
  import { currentAnalysis } from '$lib/stores/project';
</script>

<div class="max-w-5xl mx-auto space-y-8">
  <div class="flex items-center justify-between mb-6">
    <div>
      <h2 class="text-3xl font-bold tracking-tight mb-2">Script Analysis</h2>
      <p class="text-surface-400">Extracted entities and core narrative elements from the script.</p>
    </div>
    
    <div class="px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-2">
      <CheckCircle2 size={18} class="text-emerald-400" />
      <span class="text-sm font-medium text-emerald-400">Analysis Complete</span>
    </div>
  </div>
  

  {#if $currentAnalysis}
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      
      <!-- Narrative Details -->
      <div class="glass-card p-6 space-y-6 md:row-span-2">
        <h3 class="text-xl font-semibold flex items-center gap-2 text-surface-50 border-b border-surface-700 pb-4">
          <FileText size={20} class="text-brand-400" />
          Narrative Core
        </h3>
        
        <div>
          <h4 class="text-sm font-medium text-surface-400 mb-2">Core Message</h4>
          <p class="text-surface-200 leading-relaxed bg-surface-900/50 p-4 rounded-lg border border-surface-800">
            {$currentAnalysis.core_message || 'N/A'}
          </p>
        </div>

        <div>
          <h4 class="text-sm font-medium text-surface-400 mb-2">Target Audience</h4>
          <p class="text-surface-200 leading-relaxed bg-surface-900/50 p-4 rounded-lg border border-surface-800">
            {$currentAnalysis.target_audience || 'N/A'}
          </p>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div>
            <h4 class="text-sm font-medium text-surface-400 mb-2">Tone</h4>
            <div class="px-3 py-2 bg-surface-900/50 rounded-lg border border-surface-800 text-sm font-medium">
              {$currentAnalysis.tone || 'N/A'}
            </div>
          </div>
          <div>
            <h4 class="text-sm font-medium text-surface-400 mb-2">Visual Style</h4>
            <div class="px-3 py-2 bg-surface-900/50 rounded-lg border border-surface-800 text-sm font-medium">
              {$currentAnalysis.visual_style || 'N/A'}
            </div>
          </div>
        </div>
      </div>

      <!-- Entities -->
      <div class="glass-card p-6">
        <h3 class="text-lg font-semibold flex items-center gap-2 text-surface-50 border-b border-surface-700 pb-3 mb-4">
          <Users size={18} class="text-accent-primary" />
          Characters
        </h3>
        <div class="flex flex-wrap gap-2">
          {#if $currentAnalysis.characters && $currentAnalysis.characters.length > 0}
            {#each $currentAnalysis.characters as char}
              <span class="px-3 py-1.5 rounded-full bg-surface-800 border border-surface-700 text-sm font-medium">
                {char.name} <span class="text-surface-500 text-xs ml-1">({char.role})</span>
              </span>
            {/each}
          {:else}
            <span class="text-surface-500 text-sm italic">No characters detected</span>
          {/if}
        </div>
      </div>

      <div class="glass-card p-6">
        <h3 class="text-lg font-semibold flex items-center gap-2 text-surface-50 border-b border-surface-700 pb-3 mb-4">
          <MapPin size={18} class="text-emerald-400" />
          Locations
        </h3>
        <div class="flex flex-wrap gap-2">
          {#if $currentAnalysis.locations && $currentAnalysis.locations.length > 0}
            {#each $currentAnalysis.locations as loc}
              <span class="px-3 py-1.5 rounded-full bg-surface-800 border border-surface-700 text-sm font-medium">
                {loc.name} <span class="text-surface-500 text-xs ml-1">({loc.type})</span>
              </span>
            {/each}
          {:else}
            <span class="text-surface-500 text-sm italic">No locations detected</span>
          {/if}
        </div>
      </div>

      <div class="glass-card p-6 md:col-span-2">
        <h3 class="text-lg font-semibold flex items-center gap-2 text-surface-50 border-b border-surface-700 pb-3 mb-4">
          <Package size={18} class="text-orange-400" />
          Key Objects / Products
        </h3>
        <div class="flex flex-wrap gap-2">
          {#if $currentAnalysis.products && $currentAnalysis.products.length > 0}
            {#each $currentAnalysis.products as item}
              <span class="px-3 py-1.5 rounded-full bg-surface-800 border border-surface-700 text-sm font-medium">
                {item.name} <span class="text-surface-500 text-xs ml-1">({item.importance})</span>
              </span>
            {/each}
          {:else}
            <span class="text-surface-500 text-sm italic">No specific objects detected</span>
          {/if}
        </div>
      </div>

    </div>
  {:else}
    <div class="glass-card p-12 text-center flex flex-col items-center justify-center">
      <div class="w-16 h-16 rounded-full bg-surface-800 flex items-center justify-center mb-4">
        <FileText size={32} class="text-surface-500" />
      </div>
      <h3 class="text-xl font-semibold mb-2">No Analysis Available</h3>
      <p class="text-surface-400 max-w-md">
        Upload a script to generate the analysis. If you've already uploaded one, it might still be processing.
      </p>
    </div>
  {/if}
</div>
