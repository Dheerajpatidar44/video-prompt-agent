<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { ApiClient } from '$lib/api/client';
  import { currentStatus } from '$lib/stores/project';
  import { AlertCircle, HelpCircle, Loader2, Send } from '@lucide/svelte';
  import type { Question, Answer } from '$lib/types';
  import { goto } from '$app/navigation';

  let questions: Question[] = $state([]);
  let answers: Record<string, string> = $state({});
  let isLoading = $state(true);
  let isSubmitting = $state(false);
  let errorMessage = $state('');

  let threadId = $derived($page.params.threadId || '');

  onMount(async () => {
    try {
      const response = await ApiClient.getQuestions(threadId);
      // Filter out questions that have already been answered
      questions = response.questions.filter(q => q.status === 'PENDING');
      
      // Initialize answers object
      questions.forEach(q => {
        if (q.answer_type === 'BOOLEAN') {
          answers[q.id] = 'false'; // Default
        } else {
          answers[q.id] = '';
        }
      });
    } catch (error: any) {
      errorMessage = error.message || 'Failed to load questions.';
    } finally {
      isLoading = false;
    }
  });

  async function handleSubmit() {
    isSubmitting = true;
    errorMessage = '';

    const payload: Answer[] = questions.map(q => ({
      question_id: q.id,
      answer: answers[q.id],
      answer_type: q.answer_type
    }));

    // Basic validation for required fields
    const missing = questions.find(q => q.required && !answers[q.id]?.trim());
    if (missing) {
      errorMessage = `Question "${missing.question}" is required.`;
      isSubmitting = false;
      return;
    }

    try {
      const response = await ApiClient.submitAnswers(threadId, payload);
      currentStatus.set(response.status);
      
      if (response.status === 'READY' || response.status === 'PLANNING') {
        goto(`/project/${threadId}/specification`);
      } else {
        // More questions might be generated
        window.location.reload();
      }
    } catch (error: any) {
      errorMessage = error.message || 'Failed to submit answers.';
    } finally {
      isSubmitting = false;
    }
  }
</script>

<div class="max-w-3xl mx-auto space-y-8">
  <div class="mb-8">
    <h2 class="text-3xl font-bold tracking-tight mb-2 flex items-center gap-3">
      Clarification Required
      {#if !isLoading && questions.length > 0}
        <span class="px-2.5 py-0.5 rounded-full bg-brand-500/20 text-brand-400 text-sm font-semibold">
          {questions.length} Items
        </span>
      {/if}
    </h2>
    <p class="text-surface-400">
      The agent needs more information to build a complete continuity bible. Please answer the following questions.
    </p>
  </div>

  {#if isLoading}
    <div class="flex flex-col items-center justify-center py-20 text-surface-400 gap-4">
      <Loader2 size={32} class="animate-spin text-brand-500" />
      <p>Loading questions...</p>
    </div>
  {:else if errorMessage}
    <div class="p-4 rounded-lg bg-red-500/10 border border-red-500/50 flex items-start gap-3">
      <AlertCircle size={20} class="text-red-400 mt-0.5 flex-shrink-0" />
      <div class="flex-1">
        <h4 class="text-sm font-semibold text-red-400">Error</h4>
        <p class="text-sm text-red-300/80 mt-1">{errorMessage}</p>
      </div>
    </div>
  {:else if questions.length === 0}
    <div class="glass-card p-12 text-center flex flex-col items-center justify-center">
      <div class="w-16 h-16 rounded-full bg-emerald-500/20 flex items-center justify-center mb-4">
        <HelpCircle size={32} class="text-emerald-400" />
      </div>
      <h3 class="text-xl font-semibold mb-2">No Open Questions</h3>
      <p class="text-surface-400 max-w-md">
        The agent has all the information it needs. You can proceed to the specification phase.
      </p>
      <button 
        onclick={() => goto(`/project/${threadId}/specification`)}
        class="mt-6 px-6 py-2 rounded-lg bg-surface-800 hover:bg-surface-700 text-white font-medium transition-colors"
      >
        View Specification
      </button>
    </div>
  {:else}
    <div class="space-y-6">
      {#each questions as q, index}
        <div class="glass-card overflow-hidden">
          <div class="px-6 py-4 border-b border-surface-800 bg-surface-900/50 flex justify-between items-start gap-4">
            <div class="flex gap-3">
              <span class="flex-shrink-0 w-6 h-6 rounded-full bg-brand-500/20 text-brand-400 flex items-center justify-center text-sm font-bold mt-0.5">
                {index + 1}
              </span>
              <div>
                <h3 class="text-lg font-medium text-surface-50">{q.question}</h3>
                {#if q.category}
                  <span class="inline-block mt-1 text-xs font-medium text-surface-400 uppercase tracking-wider">
                    {q.category}
                  </span>
                {/if}
              </div>
            </div>
            
            {#if q.priority === 'CRITICAL'}
              <span class="px-2 py-1 rounded border border-red-500/30 bg-red-500/10 text-red-400 text-xs font-bold uppercase">
                Critical
              </span>
            {:else if q.priority === 'IMPORTANT'}
              <span class="px-2 py-1 rounded border border-orange-500/30 bg-orange-500/10 text-orange-400 text-xs font-bold uppercase">
                Important
              </span>
            {:else}
              <span class="px-2 py-1 rounded border border-surface-600 bg-surface-700 text-surface-300 text-xs font-bold uppercase">
                Optional
              </span>
            {/if}
          </div>
          
          <div class="p-6">
            {#if q.answer_type === 'MULTIPLE_CHOICE' && q.options}
              <div class="space-y-3">
                {#each q.options as opt}
                  <label class="flex items-center gap-3 p-3 rounded-lg border border-surface-700 hover:border-brand-500/50 hover:bg-brand-500/5 transition-colors cursor-pointer {answers[q.id] === opt ? 'border-brand-500 bg-brand-500/10' : ''}">
                    <input type="radio" name={q.id} value={opt} bind:group={answers[q.id]} class="text-brand-500 focus:ring-brand-500 bg-surface-950 border-surface-700" />
                    <span class="text-surface-200 text-sm font-medium">{opt}</span>
                  </label>
                {/each}
              </div>
            {:else if q.answer_type === 'BOOLEAN'}
              <div class="flex gap-4">
                <label class="flex-1 flex items-center justify-center gap-2 p-3 rounded-lg border border-surface-700 hover:border-brand-500/50 hover:bg-brand-500/5 transition-colors cursor-pointer {answers[q.id] === 'true' ? 'border-brand-500 bg-brand-500/10 text-brand-400' : 'text-surface-300'}">
                  <input type="radio" name={q.id} value="true" bind:group={answers[q.id]} class="hidden" />
                  <span class="text-sm font-medium">Yes</span>
                </label>
                <label class="flex-1 flex items-center justify-center gap-2 p-3 rounded-lg border border-surface-700 hover:border-brand-500/50 hover:bg-brand-500/5 transition-colors cursor-pointer {answers[q.id] === 'false' ? 'border-brand-500 bg-brand-500/10 text-brand-400' : 'text-surface-300'}">
                  <input type="radio" name={q.id} value="false" bind:group={answers[q.id]} class="hidden" />
                  <span class="text-sm font-medium">No</span>
                </label>
              </div>
            {:else}
              <textarea 
                bind:value={answers[q.id]} 
                placeholder="Type your answer here..."
                class="w-full bg-surface-950 border border-surface-700 rounded-lg p-3 text-sm text-surface-100 placeholder:text-surface-500 focus:outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 resize-y min-h-[100px]"
              ></textarea>
            {/if}
            
            {#if q.required}
              <p class="text-xs text-brand-400 mt-3">* This question requires an answer</p>
            {/if}
          </div>
        </div>
      {/each}

      <div class="flex justify-end pt-6">
        <button 
          onclick={handleSubmit}
          disabled={isSubmitting}
          class="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium shadow-lg shadow-brand-500/20 transition-all duration-300"
        >
          {#if isSubmitting}
            <Loader2 size={18} class="animate-spin" />
            Submitting...
          {:else}
            <Send size={18} />
            Submit Answers
          {/if}
        </button>
      </div>
    </div>
  {/if}
</div>
