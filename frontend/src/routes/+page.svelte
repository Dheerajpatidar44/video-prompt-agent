<script lang="ts">
  import { Plus, Wand2 } from '@lucide/svelte';
  // In SvelteKit we use standard <a> tags or goto()
</script>

<div class="h-full flex flex-col items-center justify-center max-w-2xl mx-auto text-center">
  <div class="w-20 h-20 rounded-2xl bg-gradient-to-br from-brand-500/20 to-accent-primary/20 flex items-center justify-center mb-8 shadow-lg border border-surface-800 backdrop-blur-sm">
    <Wand2 size={40} class="text-brand-400" />
  </div>
  
  <h1 class="text-4xl font-bold tracking-tight mb-4">
    Create intelligent <span class="text-gradient">Video Prompts</span>
  </h1>
  
  <p class="text-surface-400 text-lg mb-10 max-w-lg">
    Analyze scripts, verify continuity, and generate production-ready prompts using the Video Prompt Agent pipeline.
  </p>

  <a href="/new" class="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium shadow-lg shadow-brand-500/20 transition-all duration-300 hover:-translate-y-0.5">
    <Plus size={20} />
    New Project
  </a>
</div>
