<script lang="ts">
  import { Settings, User, Bell } from '@lucide/svelte';

  let { title = 'Workspace' } = $props<{ title?: string }>();
</script>

<header class="h-16 flex-shrink-0 glass-panel border-x-0 border-t-0 flex items-center justify-between px-8 z-10 sticky top-0">
  <h1 class="text-xl font-medium tracking-tight text-surface-50">{title}</h1>
  
  <div class="flex items-center gap-4">
    <button class="w-9 h-9 rounded-full flex items-center justify-center text-surface-400 hover:text-white hover:bg-surface-800/50 transition-colors">
      <Bell size={18} />
    </button>
    <button class="w-9 h-9 rounded-full flex items-center justify-center text-surface-400 hover:text-white hover:bg-surface-800/50 transition-colors">
      <Settings size={18} />
    </button>
    <div class="w-8 h-8 rounded-full bg-surface-800 border border-surface-700 flex items-center justify-center ml-2">
      <User size={16} class="text-surface-300" />
    </div>
  </div>
</header>
