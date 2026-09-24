<script lang="ts">
  import { page } from '$app/stores';
  import { activeThreadId } from '$lib/stores/project';
  import { onMount } from 'svelte';

  // Extract threadId from URL and set it in the store
  let threadId = $derived($page.params.threadId);

  onMount(() => {
    if (threadId) {
      activeThreadId.set(threadId);
      // Ideally we would fetch the current status of this thread from the backend here
      // and update currentStatus and the relevant step stores.
    }
  });

  let { children } = $props();
</script>

{@render children()}
