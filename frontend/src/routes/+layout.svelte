<script lang="ts">
  import '../app.css';
  let { children } = $props();
</script>

<div class="h-screen w-full bg-[#343541] text-gray-100 font-sans flex flex-col overflow-hidden">
  {@render children()}
</div>
