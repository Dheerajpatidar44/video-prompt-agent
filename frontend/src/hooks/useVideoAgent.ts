import { useState, useEffect } from "react";
import { ApiClient } from "@/lib/api/client";
import type { AgentStatus, Question, MasterScenePlan, PromptSet } from "@/lib/types";

export interface VideoAgentState {
  status: AgentStatus;
  threadId: string | null;
  gaps: any[];
  questions: Question[];
  answers: Record<string, string>;
  scenePlan: MasterScenePlan | null;
  prompts: PromptSet | null;
  error: string | null;
  isSubmitting: boolean;
}

export function useVideoAgent() {
  const [state, setState] = useState<VideoAgentState>({
    status: "IDLE",
    threadId: null,
    gaps: [],
    questions: [],
    answers: {},
    scenePlan: null,
    prompts: null,
    error: null,
    isSubmitting: false,
  });

  const setPartial = (partial: Partial<VideoAgentState>) =>
    setState((prev) => ({ ...prev, ...partial }));

  // Polling
  useEffect(() => {
    const { threadId, status } = state;
    if (!threadId) return;
    if (["IDLE", "WAITING_FOR_USER", "ERROR", "COMPLETED"].includes(status)) return;

    const interval = setInterval(async () => {
      try {
        if (status === "ANALYZING") {
          const qData = await ApiClient.getQuestions(threadId);
          if (qData.status === "WAITING_FOR_USER") {
            setPartial({ questions: qData.questions, status: "WAITING_FOR_USER" });
          } else if (["PLANNING", "GENERATING", "COMPLETED"].includes(qData.status)) {
            setPartial({ status: qData.status as AgentStatus });
          }
        }

        if (status === "PLANNING") {
          try {
            const spData = await ApiClient.getScenePlan(threadId);
            if (spData.scene_plan) {
              setPartial({ scenePlan: spData.scene_plan, status: "GENERATING" });
            }
          } catch (_) {
            // Not ready yet
          }
        }

        if (status === "GENERATING") {
          try {
            const pData = await ApiClient.getPrompts(threadId);
            if (pData.prompt_set) {
              setPartial({ prompts: pData.prompt_set, status: "COMPLETED" });
            }
          } catch (_) {
            // Not ready yet
          }
        }
      } catch (err: any) {
        console.error("[Polling error]", err);
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [state.threadId, state.status]);

  const analyzeScript = async (
    file?: File,
    text?: string,
    tool?: string,
    characterImages?: File[],
    productImages?: File[],
    brandImages?: File[]
  ) => {
    try {
      setPartial({ status: "ANALYZING", error: null, isSubmitting: true });
      const res = await ApiClient.analyzeScript(file, text, tool, characterImages, productImages, brandImages);

      let finalStatus = res.status as AgentStatus;
      let loadedQuestions: Question[] = [];
      let scenePlan = null;
      let prompts = null;

      if (finalStatus === "WAITING_FOR_USER") {
        const qData = await ApiClient.getQuestions(res.thread_id);
        loadedQuestions = qData.questions || [];
      } else if (finalStatus === "COMPLETED") {
        const spData = await ApiClient.getScenePlan(res.thread_id);
        const pData = await ApiClient.getPrompts(res.thread_id);
        scenePlan = spData.scene_plan;
        prompts = pData.prompt_set;
      }

      setPartial({
        threadId: res.thread_id,
        status: finalStatus,
        gaps: res.gaps || [],
        questions: loadedQuestions,
        scenePlan,
        prompts,
        isSubmitting: false
      });
    } catch (err: any) {
      setPartial({ error: err.message || "Failed to analyze script", status: "ERROR", isSubmitting: false });
    }
  };

  const submitAnswers = async () => {
    if (!state.threadId) return;
    try {
      setPartial({ status: "PLANNING", isSubmitting: true });
      const formattedAnswers = state.questions.map((q) => ({
        question_id: q.id,
        answer: state.answers[q.id] || "No answer provided",
        answer_type: q.answer_type,
      }));
      const res = await ApiClient.submitAnswers(state.threadId, formattedAnswers);

      let finalStatus = res.status as AgentStatus;
      let scenePlan = null;
      let prompts = null;
      let questions = state.questions;

      if (finalStatus === "WAITING_FOR_USER") {
        const qData = await ApiClient.getQuestions(state.threadId);
        questions = qData.questions || [];
      } else if (finalStatus === "COMPLETED") {
        const spData = await ApiClient.getScenePlan(state.threadId);
        const pData = await ApiClient.getPrompts(state.threadId);
        scenePlan = spData.scene_plan;
        prompts = pData.prompt_set;
      }

      setPartial({
        status: finalStatus,
        gaps: res.gaps || state.gaps,
        questions,
        ...(scenePlan && { scenePlan }),
        ...(prompts && { prompts }),
        isSubmitting: false
      });
    } catch (err: any) {
      setPartial({ error: err.message || "Failed to submit answers", status: "ERROR", isSubmitting: false });
    }
  };

  const setAnswer = (questionId: string, answer: string) => {
    setPartial({ answers: { ...state.answers, [questionId]: answer } });
  };

  const reset = () =>
    setState({
      status: "IDLE",
      threadId: null,
      gaps: [],
      questions: [],
      answers: {},
      scenePlan: null,
      prompts: null,
      error: null,
      isSubmitting: false,
    });

  return { state, analyzeScript, submitAnswers, setAnswer, reset };
}
