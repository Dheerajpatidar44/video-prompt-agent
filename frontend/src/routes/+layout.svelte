<script lang="ts">
  import '../app.css';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import Topbar from '$lib/components/Topbar.svelte';
  import { page } from '$app/stores';
  import { activeThreadId, currentStatus } from '$lib/stores/project';
  
  let { children } = $props();

  let title = $derived($page.url.pathname === '/' 
    ? 'Dashboard' 
    : $page.url.pathname.split('/').pop()?.replace(/^\w/, c => c.toUpperCase()) || 'Workspace');
</script>

<div class="flex h-screen bg-surface-950 overflow-hidden text-surface-50">
  <Sidebar activeThreadId={$activeThreadId} currentStatus={$currentStatus} />
  
  <main class="flex-1 flex flex-col min-w-0 overflow-hidden relative">
    <Topbar {title} />
    
    <div class="flex-1 overflow-y-auto p-8 relative z-0">
      {@render children()}
    </div>
  </main>
</div>
