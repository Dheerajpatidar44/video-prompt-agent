<script lang="ts">
  import { 
    LayoutDashboard, 
    FileText, 
    MessageSquare, 
    Film, 
    Clapperboard, 
    Wand2 
  } from '@lucide/svelte';

  let { 
    activeThreadId = null,
    currentStatus = 'IDLE'
  } = $props<{ activeThreadId?: string | null; currentStatus?: string }>();

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard, path: '/' },
    { id: 'analysis', label: 'Analysis', icon: FileText, path: '/analysis', requiresThread: true },
    { id: 'questions', label: 'Clarification', icon: MessageSquare, path: '/questions', requiresThread: true },
    { id: 'specification', label: 'Specification', icon: Film, path: '/specification', requiresThread: true },
    { id: 'scenes', label: 'Scene Plan', icon: Clapperboard, path: '/scenes', requiresThread: true },
    { id: 'prompts', label: 'Prompts', icon: Wand2, path: '/prompts', requiresThread: true }
  ];

  function getPath(item: typeof navItems[0]) {
    if (item.requiresThread && activeThreadId) {
      return `/project/${activeThreadId}${item.path}`;
    }
    return item.path;
  }
</script>

<aside class="w-64 h-screen flex-shrink-0 glass-panel border-y-0 border-l-0 flex flex-col z-20">
  <div class="p-6 flex items-center gap-3 border-b border-surface-800/50">
    <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-500 to-accent-primary flex items-center justify-center shadow-lg">
      <Wand2 size={18} class="text-white" />
    </div>
    <span class="font-bold text-lg tracking-tight">Video Agent</span>
  </div>

  <nav class="flex-1 overflow-y-auto py-6 px-4 space-y-1">
    {#each navItems as item}
      {@const isDisabled = item.requiresThread && !activeThreadId}
      {@const Icon = item.icon}
      <a 
        href={isDisabled ? '#' : getPath(item)} 
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200
               {isDisabled 
                 ? 'opacity-40 cursor-not-allowed text-surface-400' 
                 : 'text-surface-300 hover:text-white hover:bg-surface-800/50'}"
        onclick={(e) => { if (isDisabled) e.preventDefault(); }}
      >
        <Icon size={18} class={isDisabled ? 'text-surface-500' : 'text-brand-400'} />
        {item.label}
      </a>
    {/each}
  </nav>

  <div class="p-4 mt-auto border-t border-surface-800/50">
    <div class="flex items-center gap-3 px-3 py-2 bg-surface-950/50 rounded-lg border border-surface-800/50">
      <div class="relative flex h-3 w-3">
        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand-400 opacity-75"></span>
        <span class="relative inline-flex rounded-full h-3 w-3 bg-brand-500"></span>
      </div>
      <div class="flex flex-col">
        <span class="text-xs font-semibold text-surface-200">System Status</span>
        <span class="text-[10px] text-surface-400 font-mono">{currentStatus}</span>
      </div>
    </div>
  </div>
</aside>
