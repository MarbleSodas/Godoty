/**
 * TypeScript interfaces for backend API responses
 * Provides type safety for API key management and configuration endpoints
 */

import { AvailableModel } from '../services/config.service';

/**
 * Response from backend configuration endpoint (/config)
 * Contains available models and API key status information
 */
export interface BackendConfigResponse {
  available_models?: AvailableModel[];
  has_api_key?: boolean;
  has_backend_key?: boolean;
  api_key_configured?: boolean;
  api_key_source?: 'environment' | 'user_override' | 'none';
  api_key_prefix?: string;
  allow_user_override?: boolean;
  default_model?: string;
  app_name?: string;
  app_version?: string;
  cost_warning_threshold?: number;
  enable_metrics?: boolean;
  openrouter_base_url?: string;
}

/**
 * Response from backend connection status endpoint (/connection/status)
 * Contains detailed API key and connection information
 */
export interface ConnectionStatusResponse {
  connected?: boolean;
  has_api_key?: boolean;
  has_backend_key?: boolean;
  api_key_configured?: boolean;
  api_key_source?: 'environment' | 'user_override' | 'none';
  api_key_prefix?: string;
  allow_user_override?: boolean;
  model_id?: string;
  provider?: string;
  base_url?: string;
  error?: string;
  // Nested API key status object for frontend compatibility
  apiKeyStatus?: {
    hasKey: boolean;
    hasBackendKey: boolean;
    allowUserOverride: boolean;
    apiKeyPrefix?: string;
  };
}

/**
 * API key status interface used throughout the application
 * This is the canonical type for API key state management
 */
export interface ApiKeyStatus {
  hasKey: boolean;
  source: 'environment' | 'user_override' | 'none';
  needsUserInput: boolean;
  hasBackendKey: boolean;
  apiKeyPrefix?: string;
  allowUserOverride: boolean;
}

/**
 * Type guard to check if an object is a valid BackendConfigResponse
 */
export function isBackendConfigResponse(obj: any): obj is BackendConfigResponse {
  return obj && typeof obj === 'object';
}

/**
 * Type guard to check if an object is a valid ConnectionStatusResponse
 */
export function isConnectionStatusResponse(obj: any): obj is ConnectionStatusResponse {
  return obj && typeof obj === 'object';
}

/**
 * Helper function to safely extract API key status from a backend response
 */
export function extractApiKeyStatus(response: BackendConfigResponse | ConnectionStatusResponse): ApiKeyStatus {
  // Check for the new nested apiKeyStatus object first (from connection/status endpoint)
  if ('apiKeyStatus' in response && response.apiKeyStatus) {
    const hasUserKey = !!localStorage.getItem('godoty_openrouter_key');

    return {
      hasKey: response.apiKeyStatus.hasKey || hasUserKey,
      source: response.apiKeyStatus.hasBackendKey
        ? 'environment'
        : (hasUserKey ? 'user_override' : 'none'),
      needsUserInput: !response.apiKeyStatus.hasKey && !hasUserKey,
      hasBackendKey: response.apiKeyStatus.hasBackendKey,
      apiKeyPrefix: response.apiKeyStatus.apiKeyPrefix,
      allowUserOverride: response.apiKeyStatus.allowUserOverride !== false
    };
  }

  // Fall back to the legacy structure (from /config endpoint)
  const hasBackendKey = response.has_backend_key || response.api_key_configured || false;
  const hasUserKey = !!localStorage.getItem('godoty_openrouter_key');

  return {
    hasKey: hasBackendKey || hasUserKey,
    source: hasBackendKey
      ? (response.api_key_source || 'environment')
      : (hasUserKey ? 'user_override' : 'none'),
    needsUserInput: !hasBackendKey && !hasUserKey,
    hasBackendKey,
    apiKeyPrefix: response.api_key_prefix,
    allowUserOverride: response.allow_user_override !== false
  };
}