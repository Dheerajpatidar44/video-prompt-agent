import { useState, useEffect } from "react";
import { ApiClient } from "@/lib/api/client";
import type { AgentStatus, Question, MasterScenePlan, PromptSet } from "@/lib/types";

export interface VideoAgentState {
  status: AgentStatus;
  threadId: string | null;
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
    }, 3000);

    return () => clearInterval(interval);
  }, [state.threadId, state.status]);

  const analyzeScript = async (file?: File, text?: string) => {
    try {
      setPartial({ status: "ANALYZING", error: null, isSubmitting: true });
      const res = await ApiClient.analyzeScript(file, text);
      setPartial({ threadId: res.thread_id, status: res.status, isSubmitting: false });
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
      await ApiClient.submitAnswers(state.threadId, formattedAnswers);
      setPartial({ isSubmitting: false });
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
      questions: [],
      answers: {},
      scenePlan: null,
      prompts: null,
      error: null,
      isSubmitting: false,
    });

  return { state, analyzeScript, submitAnswers, setAnswer, reset };
}
