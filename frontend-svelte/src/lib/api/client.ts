import type { AnalyzeResponse, Question, Answer, VideoSpecification, MasterScenePlan, PromptSet } from '../types';

// In a real app, this should come from process.env or $env/static/public
const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

export class ApiClient {
  private static async handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
      let errorMessage = response.statusText;
      try {
        const errorData = await response.json();
        errorMessage = errorData.detail || errorData.error || errorMessage;
      } catch (e) {
        // Fallback to text
      }
      throw new Error(errorMessage);
    }
    return response.json();
  }

  static async analyzeScript(file?: File, text?: string): Promise<AnalyzeResponse> {
    const formData = new FormData();
    if (file) {
      formData.append('file', file);
    } else if (text) {
      formData.append('text', text);
    } else {
      throw new Error('Must provide either file or text');
    }

    const response = await fetch(`${API_BASE_URL}/scripts/analyze`, {
      method: 'POST',
      body: formData,
    });
    
    return this.handleResponse<AnalyzeResponse>(response);
  }

  static async getQuestions(threadId: string): Promise<{ thread_id: string; questions: Question[]; status: string }> {
    const response = await fetch(`${API_BASE_URL}/scripts/${threadId}/questions`);
    return this.handleResponse(response);
  }

  static async submitAnswers(threadId: string, answers: Answer[]): Promise<any> {
    const response = await fetch(`${API_BASE_URL}/scripts/${threadId}/answers`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ answers }),
    });
    return this.handleResponse(response);
  }

  static async getSpecification(threadId: string): Promise<{ thread_id: string; video_specification: VideoSpecification; status: string }> {
    const response = await fetch(`${API_BASE_URL}/scripts/${threadId}/video-specification`);
    return this.handleResponse(response);
  }

  static async getScenePlan(threadId: string): Promise<{ thread_id: string; scene_plan: MasterScenePlan; status: string }> {
    const response = await fetch(`${API_BASE_URL}/scripts/${threadId}/scene-plan`);
    return this.handleResponse(response);
  }

  static async getPrompts(threadId: string): Promise<{ thread_id: string; prompt_set: PromptSet; status: string }> {
    const response = await fetch(`${API_BASE_URL}/scripts/${threadId}/prompts`);
    return this.handleResponse(response);
  }
}
