import { useState, useEffect } from "react";
import { ApiClient } from "@/lib/api/client";
import type { AgentStatus, Question, MasterScenePlan, PromptSet, ProjectImagesResponse } from "@/lib/types";

export interface VideoAgentState {
  status: AgentStatus;
  threadId: string | null;
  gaps: any[];
  questions: Question[];
  answers: Record<string, string>;
  scenePlan: MasterScenePlan | null;
  prompts: PromptSet | null;
  reviewReport: any | null;
  error: string | null;
  isSubmitting: boolean;
  videoStatus: string | null;
  finalVideoUrl: string | null;
  completedShots?: number;
  totalShots?: number;
  isStitching?: boolean;
  projectImages?: ProjectImagesResponse | null;
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
    reviewReport: null,
    error: null,
    isSubmitting: false,
    videoStatus: null,
    finalVideoUrl: null,
    completedShots: 0,
    totalShots: 0,
    isStitching: false,
    projectImages: null,
  });

  const setPartial = (partial: Partial<VideoAgentState>) =>
    setState((prev) => ({ ...prev, ...partial }));

  const loadPhase1Assets = async (threadId: string) => {
    const [spData, pData, imgData] = await Promise.all([
      ApiClient.getScenePlan(threadId).catch(() => ({ scene_plan: null })),
      ApiClient.getPrompts(threadId).catch(() => ({ prompt_set: null, review_report: null })),
      ApiClient.getProjectImages(threadId).catch(() => null),
    ]);
    return {
      scenePlan: spData.scene_plan || null,
      prompts: pData.prompt_set || null,
      reviewReport: pData.review_report || null,
      projectImages: imgData || null,
    };
  };

  // Polling
  useEffect(() => {
    const { threadId, status, videoStatus, finalVideoUrl } = state;
    if (!threadId) return;
    if (["IDLE", "WAITING_FOR_USER", "PROMPTS_READY", "ERROR"].includes(status)) return;
    const isTerminalVideoState =
      videoStatus === "FAILED" ||
      videoStatus === "COMPLETED" ||
      videoStatus === "PARTIAL_FAILURE" ||
      !!finalVideoUrl;
    if ((status === "COMPLETED" || status === "GENERATING_VIDEOS") && isTerminalVideoState) return;

    const interval = setInterval(async () => {
      try {
        if (status === "ANALYZING") {
          const qData = await ApiClient.getQuestions(threadId);
          if (qData.status === "WAITING_FOR_USER") {
            setPartial({ questions: qData.questions, status: "WAITING_FOR_USER" });
          } else if (qData.status === "PROMPTS_READY") {
            const assets = await loadPhase1Assets(threadId);
            setPartial({ ...assets, status: "PROMPTS_READY" });
          } else if (qData.status === "ERROR") {
            setPartial({ status: "ERROR", error: "Script analysis encountered an error." });
          } else if (["PLANNING", "GENERATING", "REVIEWING", "GENERATING_VIDEOS", "COMPLETED"].includes(qData.status)) {
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
            if (pData.status === "REVIEWING") {
              setPartial({ status: "REVIEWING" });
            } else if ((pData.status === "PROMPTS_READY" || pData.status === "GENERATING_VIDEOS") && pData.prompt_set) {
              const assets = await loadPhase1Assets(threadId);
              setPartial({
                ...assets,
                prompts: pData.prompt_set,
                reviewReport: pData.review_report || assets.reviewReport,
                status: pData.status as AgentStatus,
              });
            }
          } catch (_) {
            // Not ready yet
          }
        }

        if (status === "REVIEWING") {
          try {
            const pData = await ApiClient.getPrompts(threadId);
            if ((pData.status === "PROMPTS_READY" || pData.status === "GENERATING_VIDEOS") && pData.prompt_set) {
              const assets = await loadPhase1Assets(threadId);
              setPartial({
                ...assets,
                prompts: pData.prompt_set,
                reviewReport: pData.review_report || assets.reviewReport,
                status: pData.status as AgentStatus,
              });
            }
          } catch (_) {
            // Not ready yet
          }
        }

        if ((status === "COMPLETED" || status === "GENERATING_VIDEOS") && (!finalVideoUrl || (videoStatus !== "COMPLETED" && videoStatus !== "FAILED" && videoStatus !== "PARTIAL_FAILURE"))) {
          try {
            const vData = await ApiClient.getVideoStatus(threadId);
            if (vData.status === "NOT_STARTED") {
              return;
            }
            const allTerminal =
              vData.total_shots > 0 &&
              vData.completed_shots + (vData.failed_shots || 0) === vData.total_shots;
            const isStitching =
              (vData.status === "IN_PROGRESS" || vData.status === "STITCHING") &&
              vData.completed_shots > 0 &&
              allTerminal &&
              !vData.final_video_url;

            if (vData.final_video_url) {
              const imgData = await ApiClient.getProjectImages(threadId).catch(() => null);
              setPartial({
                videoStatus: vData.status,
                finalVideoUrl: vData.final_video_url,
                completedShots: vData.completed_shots,
                totalShots: vData.total_shots,
                isStitching: false,
                error: vData.status === "PARTIAL_FAILURE" ? (vData.error_message || "Some shots failed during generation.") : null,
                ...(imgData && { projectImages: imgData }),
              });
            } else if (vData.status === "FAILED" || vData.status === "PARTIAL_FAILURE" || vData.status === "COMPLETED") {
              const failedJobError = vData.jobs?.find((j: any) => j.error_message)?.error_message;
              const imgData = await ApiClient.getProjectImages(threadId).catch(() => null);
              setPartial({
                videoStatus: "FAILED",
                finalVideoUrl: null,
                completedShots: vData.completed_shots,
                totalShots: vData.total_shots,
                isStitching: false,
                error: vData.error_message || failedJobError || "Video generation or stitching failed.",
                ...(imgData && { projectImages: imgData }),
              });
            } else {
              setPartial({
                videoStatus: isStitching ? "STITCHING" : vData.status,
                completedShots: vData.completed_shots,
                totalShots: vData.total_shots,
                isStitching,
              });
            }
          } catch (_) {
            // Not ready yet
          }
        }
      } catch (err: any) {
        console.error("[Polling error]", err);
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [state.threadId, state.status, state.videoStatus, state.finalVideoUrl]);

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
      if (finalStatus === "ERROR" || res.error) {
        setPartial({
          threadId: res.thread_id,
          status: "ERROR",
          error: res.error || "Failed to analyze script",
          isSubmitting: false,
        });
        return res;
      }

      let loadedQuestions: Question[] = [];
      let scenePlan = null;
      let prompts = null;
      let reviewReport = null;
      let projectImages = null;

      if (finalStatus === "WAITING_FOR_USER") {
        const qData = await ApiClient.getQuestions(res.thread_id);
        loadedQuestions = qData.questions || [];
      } else if (
        finalStatus === "PROMPTS_READY" ||
        finalStatus === "COMPLETED" ||
        finalStatus === "GENERATING_VIDEOS"
      ) {
        const assets = await loadPhase1Assets(res.thread_id);
        scenePlan = assets.scenePlan;
        prompts = assets.prompts;
        reviewReport = assets.reviewReport;
        projectImages = assets.projectImages;
      }

      setPartial({
        threadId: res.thread_id,
        status: finalStatus,
        gaps: res.gaps || [],
        questions: loadedQuestions,
        scenePlan,
        prompts,
        reviewReport,
        ...(projectImages && { projectImages }),
        isSubmitting: false
      });
      return res;
    } catch (err: any) {
      setPartial({ error: err.message || "Failed to analyze script", status: "ERROR", isSubmitting: false });
    }
  };

  const submitAnswers = async () => {
    if (!state.threadId) return;
    try {
      setPartial({ status: "PLANNING", isSubmitting: true, error: null });
      const formattedAnswers = state.questions.map((q) => ({
        question_id: q.id,
        answer: state.answers[q.id] || "No answer provided",
        answer_type: q.answer_type,
      }));
      const res = await ApiClient.submitAnswers(state.threadId, formattedAnswers);

      let finalStatus = res.status as AgentStatus;
      if (finalStatus === "ERROR" || res.error) {
        setPartial({
          status: "ERROR",
          error: res.error || "Failed to generate scene plan and prompts",
          isSubmitting: false,
        });
        return res;
      }

      let scenePlan = null;
      let prompts = null;
      let reviewReport = null;
      let projectImages = null;
      let questions = state.questions;

      if (finalStatus === "WAITING_FOR_USER") {
        const qData = await ApiClient.getQuestions(state.threadId);
        questions = qData.questions || [];
      } else if (
        finalStatus === "PROMPTS_READY" ||
        finalStatus === "COMPLETED" ||
        finalStatus === "GENERATING_VIDEOS"
      ) {
        const assets = await loadPhase1Assets(state.threadId);
        scenePlan = assets.scenePlan;
        prompts = assets.prompts;
        reviewReport = assets.reviewReport;
        projectImages = assets.projectImages;
      }

      setPartial({
        status: finalStatus,
        gaps: res.gaps || state.gaps,
        questions,
        ...(scenePlan && { scenePlan }),
        ...(prompts && { prompts }),
        ...(reviewReport && { reviewReport }),
        ...(projectImages && { projectImages }),
        isSubmitting: false
      });
      return res;
    } catch (err: any) {
      setPartial({ error: err.message || "Failed to submit answers", status: "ERROR", isSubmitting: false });
    }
  };

  const startVideoGeneration = async () => {
    if (!state.threadId || state.isSubmitting) return;
    try {
      setPartial({ isSubmitting: true, error: null });
      const res = await ApiClient.startVideoGeneration(state.threadId);
      if (res.status === "BLOCKED_COST_GUARD") {
        setPartial({
          videoStatus: "BLOCKED_COST_GUARD",
          error: res.message || "Video generation blocked by project safety limits.",
          isSubmitting: false,
        });
        return res;
      }
      setPartial({
        status: "GENERATING_VIDEOS",
        videoStatus: "IN_PROGRESS",
        isSubmitting: false,
      });
      return res;
    } catch (err: any) {
      setPartial({
        error: err.message || "Failed to start video generation",
        isSubmitting: false,
      });
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
      reviewReport: null,
      error: null,
      isSubmitting: false,
      videoStatus: null,
      finalVideoUrl: null,
      completedShots: 0,
      totalShots: 0,
      isStitching: false,
      projectImages: null,
    });

  return { state, analyzeScript, submitAnswers, startVideoGeneration, setAnswer, reset };
}
