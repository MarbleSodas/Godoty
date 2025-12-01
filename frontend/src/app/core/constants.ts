export const APP_CONFIG = {
  // Backend API Configuration
  API_BASE_URL: 'http://localhost:8000',
  API_ENDPOINTS: {
    BASE: 'http://localhost:8000',
    CHAT: 'http://localhost:8000/api/godoty',
    STATUS: 'http://localhost:8000/api/godot/status',
    CONNECTION_STATUS: 'http://localhost:8000/api/godoty/connection/status',
    HEALTH: 'http://localhost:8000/api/godoty/health',
    SSE: 'http://localhost:8000/api'
  },

  // Godot Configuration (Backend defaults)
  GODOT_WEBSOCKET_PORT: 9001,
  GODOT_AUTO_CONNECT: true,

  // OpenRouter Configuration
  OPENROUTER_API_BASE: 'https://openrouter.ai/api/v1',
  DEFAULT_PLANNING_MODEL: 'x-ai/grok-4.1-fast',

  // Features (Always enabled)
  COST_TRACKING_ENABLED: true,
  DEFAULT_COST_WARNING_THRESHOLD: 1.0, // $1.00

  // Connection States
  CONNECTION_STATES: {
    CONNECTED: 'connected',
    DISCONNECTED: 'disconnected',
    CONNECTING: 'connecting'
  }
} as const;