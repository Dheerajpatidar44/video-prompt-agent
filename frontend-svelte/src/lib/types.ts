export type AgentStatus = 
  | 'IDLE' 
  | 'ANALYZING' 
  | 'WAITING_FOR_USER' 
  | 'PLANNING' 
  | 'GENERATING' 
  | 'VALIDATING' 
  | 'COMPLETED' 
  | 'ERROR';

export type SpecSource = 'SCRIPT' | 'USER' | 'INFERRED' | 'SYSTEM_DEFAULT';

export interface TraceableValue {
  value: string;
  source: SpecSource;
  confidence: number;
  original_context?: string;
  inferred_reasoning?: string;
}

export interface ScriptAnalysis {
  project_id: string;
  characters: any[];
  locations: any[];
  products: any[];
  core_message: string;
  target_audience: string;
  tone: string;
  visual_style: string;
}

export interface AnalyzeResponse {
  thread_id: string;
  status: AgentStatus;
  script?: any;
  analysis?: ScriptAnalysis;
  gaps?: any;
  error?: string;
}

export interface Question {
  id: string;
  gap_ids: string[];
  question: string;
  category: string;
  priority: 'CRITICAL' | 'IMPORTANT' | 'OPTIONAL';
  answer_type: 'TEXT' | 'MULTIPLE_CHOICE' | 'BOOLEAN';
  options?: string[];
  required: boolean;
  round_number: number;
  answer?: string;
  status: 'PENDING' | 'ANSWERED' | 'SKIPPED';
}

export interface Answer {
  question_id: string;
  answer: string;
  answer_type: string;
}

export interface VideoSpecification {
  project_id: string;
  title: string;
  output_requirements: any;
  characters: any[];
  locations: any[];
  products: any[];
  actions: any[];
  camera: any;
  lighting: any;
  composition: any;
  visual_style: any;
  audio: any;
  continuity_bible: any;
  unresolved_items: any[];
  status: string;
}

export interface ScenePlan {
  scene_id: string;
  scene_number: number;
  title: string;
  purpose: string;
  narrative_role: string;
  start_time: number;
  end_time: number;
  duration_seconds: number;
  location: string;
  characters_involved: string[];
  lighting_setup: string;
  audio_elements: string[];
  shots: ShotPlan[];
}

export interface ShotPlan {
  shot_id: string;
  shot_number: string;
  scene_id: string;
  start_time: number;
  end_time: number;
  duration_seconds: number;
  purpose: string;
  subject: string;
  action: string;
  framing: string;
  camera_movement: string;
  camera_angle: string;
  lens_type: string;
  lighting_adjustments: string;
  vfx_requirements: string;
}

export interface MasterScenePlan {
  scenes: ScenePlan[];
  total_duration: number;
  status: string;
  validation_issues: any[];
}

export interface GeneratedPrompt {
  prompt_id: string;
  scene_id: string;
  shot_id: string;
  sequence_number: number;
  duration_seconds: number;
  prompt_text: string;
  negative_constraints: string;
  camera_parameters: string;
  lighting_parameters: string;
  motion_parameters: string;
  subject_description: string;
  environment_description: string;
  style_modifiers: string;
}

export interface PromptSet {
  prompts: GeneratedPrompt[];
  total_duration: number;
  aspect_ratio: string;
  status: string;
  validation_issues: any[];
}
