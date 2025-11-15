export interface RagStatus {
  running: boolean;
  port?: number | null;
  last_error?: string | null;
}

export interface DetailedRagStatus {
  running: boolean;
  port?: number | null;
  last_error?: string | null;
  executable_type: string;
  script_path?: string | null;
  can_fallback_to_python: boolean;
  suggestions: string[];
}

export interface SidecarServices {
  litellm: {
    running: boolean;
    port?: number | null;
    last_error?: string | null;
  };
  rag: {
    running: boolean;
    port?: number | null;
    last_error?: string | null;
    executable_type: string;
    can_fallback_to_python: boolean;
    suggestions: string[];
  };
}