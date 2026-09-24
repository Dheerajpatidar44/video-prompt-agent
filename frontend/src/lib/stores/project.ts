import { writable } from 'svelte/store';
import type { AgentStatus, ScriptAnalysis, VideoSpecification, MasterScenePlan, PromptSet } from '../types';

export const activeThreadId = writable<string | null>(null);
export const currentStatus = writable<AgentStatus>('IDLE');

// Caches for the current project
export const currentAnalysis = writable<ScriptAnalysis | null>(null);
export const currentSpecification = writable<VideoSpecification | null>(null);
export const currentScenePlan = writable<MasterScenePlan | null>(null);
export const currentPromptSet = writable<PromptSet | null>(null);

export function resetProject() {
  activeThreadId.set(null);
  currentStatus.set('IDLE');
  currentAnalysis.set(null);
  currentSpecification.set(null);
  currentScenePlan.set(null);
  currentPromptSet.set(null);
}
