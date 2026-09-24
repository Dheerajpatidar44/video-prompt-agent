<script lang="ts">
  import { FileText, UploadCloud, ArrowRight, Loader2, Play } from '@lucide/svelte';
  import { goto } from '$app/navigation';
  import { ApiClient } from '$lib/api/client';
  import { activeThreadId, currentStatus, currentAnalysis } from '$lib/stores/project';

  let textInput = $state('');
  let selectedFile: File | null = $state(null);
  let isSubmitting = $state(false);
  let errorMessage = $state('');

  function handleFileChange(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      selectedFile = input.files[0];
      textInput = ''; // Clear text if file is uploaded
    }
  }

  async function handleSubmit() {
    if (!textInput.trim() && !selectedFile) {
      errorMessage = 'Please provide either a script file or text.';
      return;
    }

    isSubmitting = true;
    errorMessage = '';

    try {
      const response = await ApiClient.analyzeScript(selectedFile || undefined, textInput || undefined);
      
      // Update global stores
      activeThreadId.set(response.thread_id);
      currentStatus.set(response.status);
      if (response.analysis) {
        currentAnalysis.set(response.analysis);
      }
      
      // Redirect to next step based on status
      if (response.status === 'WAITING_FOR_USER') {
        goto(`/project/${response.thread_id}/questions`);
      } else {
        goto(`/project/${response.thread_id}/analysis`);
      }
    } catch (error: any) {
      errorMessage = error.message || 'Failed to start project.';
    } finally {
      isSubmitting = false;
    }
  }
</script>

<div class="max-w-4xl mx-auto py-12">
  <div class="mb-10 text-center">
    <h2 class="text-3xl font-bold tracking-tight mb-3">Create New Project</h2>
    <p class="text-surface-400 max-w-lg mx-auto">
      Upload your video script or paste it directly. We'll analyze it to extract characters, locations, and narrative goals.
    </p>
  </div>

  <div class="glass-card p-8">
    {#if errorMessage}
      <div class="mb-6 p-4 rounded-lg bg-red-500/10 border border-red-500/50 text-red-400 text-sm">
        {errorMessage}
      </div>
    {/if}

    <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
      
      <!-- File Upload Area -->
      <div class="flex flex-col">
        <label class="text-sm font-medium text-surface-200 mb-3 flex items-center gap-2">
          <UploadCloud size={16} />
          Upload Script File (.txt or .pdf)
        </label>
        
        <div class="flex-1 relative border-2 border-dashed border-surface-700 rounded-xl hover:border-brand-500/50 transition-colors bg-surface-900/50 flex flex-col items-center justify-center p-8 group">
          <input 
            type="file" 
            accept=".txt,.pdf" 
            onchange={handleFileChange}
            class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
          />
          <div class="w-12 h-12 rounded-full bg-surface-800 flex items-center justify-center mb-4 group-hover:bg-brand-500/20 group-hover:text-brand-400 transition-colors">
            {#if selectedFile}
              <FileText size={24} class="text-brand-400" />
            {:else}
              <UploadCloud size={24} />
            {/if}
          </div>
          <span class="font-medium text-surface-200 mb-1">
            {selectedFile ? selectedFile.name : 'Click or drag file to upload'}
          </span>
          <span class="text-xs text-surface-500">
            {selectedFile ? `${(selectedFile.size / 1024).toFixed(1)} KB` : 'Maximum file size 5MB'}
          </span>
        </div>
      </div>

      <!-- Text Paste Area -->
      <div class="flex flex-col">
        <label class="text-sm font-medium text-surface-200 mb-3 flex items-center gap-2">
          <FileText size={16} />
          Or paste script text
        </label>
        <textarea 
          bind:value={textInput}
          placeholder="INT. COFFEE SHOP - DAY\n\nJOHN sits at the table..."
          class="flex-1 w-full bg-surface-900/50 border border-surface-700 rounded-xl p-4 text-sm text-surface-100 placeholder:text-surface-600 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 resize-none min-h-[240px]"
          disabled={!!selectedFile}
        ></textarea>
        {#if selectedFile}
          <div class="absolute inset-0 bg-surface-950/60 backdrop-blur-[1px] rounded-xl flex items-center justify-center">
            <span class="text-sm font-medium text-surface-400">File selected</span>
          </div>
        {/if}
      </div>

    </div>

    <div class="mt-8 pt-8 border-t border-surface-800 flex justify-end">
      <button 
        onclick={handleSubmit}
        disabled={isSubmitting || (!textInput.trim() && !selectedFile)}
        class="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium shadow-lg shadow-brand-500/20 transition-all duration-300 w-full md:w-auto"
      >
        {#if isSubmitting}
          <Loader2 size={20} class="animate-spin" />
          Analyzing Script...
        {:else}
          <Play size={18} fill="currentColor" />
          Start Analysis
        {/if}
      </button>
    </div>
  </div>
</div>
