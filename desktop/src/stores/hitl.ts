import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type ActionType = 
  | 'write_file'
  | 'delete_file'
  | 'create_node'
  | 'delete_node'
  | 'set_project_setting'
  | 'create_directory'
  | 'rename_file'
  | 'move_file'
  | 'copy_file'

export interface HitlPreferences {
  alwaysAllowAll: boolean
  alwaysAllow: Record<ActionType, boolean>
}

// localStorage key
const PREFERENCES_KEY = 'godoty_hitl_preferences'

export const useHitlStore = defineStore('hitl', () => {
  // State
  const preferences = ref<HitlPreferences>({
    alwaysAllowAll: false,
    alwaysAllow: {
      write_file: false,
      delete_file: false,
      create_node: false,
      delete_node: false,
      set_project_setting: false,
      create_directory: false,
      rename_file: false,
      move_file: false,
      copy_file: false,
    }
  })

  // Private sender function to avoid circular dependency with brain store
  let sendRequestFn: ((method: string, params?: Record<string, unknown>) => Promise<unknown>) | null = null

  // Computed
  const isAutoApproveEnabled = computed(() => (action: ActionType) => {
    if (preferences.value.alwaysAllowAll) return true
    return preferences.value.alwaysAllow[action] || false
  })

  const autoApproveCount = computed(() => {
    if (preferences.value.alwaysAllowAll) return Object.keys(preferences.value.alwaysAllow).length
    return Object.values(preferences.value.alwaysAllow).filter(v => v).length
  })

  // Actions
  function setSendRequest(fn: (method: string, params?: Record<string, unknown>) => Promise<unknown>) {
    sendRequestFn = fn
  }

  function initialize() {
    try {
      const stored = localStorage.getItem(PREFERENCES_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        // Merge with defaults to handle new keys in future
        preferences.value = {
          alwaysAllowAll: parsed.alwaysAllowAll ?? false,
          alwaysAllow: { ...preferences.value.alwaysAllow, ...parsed.alwaysAllow }
        }
      }
    } catch (e) {
      console.warn('Failed to load HITL preferences:', e)
    }
  }

  function savePreferences() {
    try {
      localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences.value))
      syncToBrain()
    } catch (e) {
      console.warn('Failed to save HITL preferences:', e)
    }
  }

  async function syncToBrain() {
    if (!sendRequestFn) return

    try {
      // Map frontend camelCase to backend snake_case if needed
      // Current requirement: "always_allow_all" and "always_allow"
      await sendRequestFn('set_hitl_preferences', {
        always_allow_all: preferences.value.alwaysAllowAll,
        always_allow: preferences.value.alwaysAllow
      })
    } catch (e) {
      console.warn('Failed to sync HITL preferences to brain:', e)
    }
  }

  function setAlwaysAllowAll(value: boolean) {
    preferences.value.alwaysAllowAll = value
    savePreferences()
  }

  function setAlwaysAllowAction(action: ActionType, value: boolean) {
    preferences.value.alwaysAllow[action] = value
    savePreferences()
  }

  function resetToDefaults() {
    preferences.value.alwaysAllowAll = false
    Object.keys(preferences.value.alwaysAllow).forEach(key => {
      preferences.value.alwaysAllow[key as ActionType] = false
    })
    savePreferences()
  }

  // Initialize immediately
  initialize()

  return {
    // State
    preferences,
    
    // Computed
    isAutoApproveEnabled,
    autoApproveCount,
    
    // Actions
    setSendRequest,
    syncToBrain,
    setAlwaysAllowAll,
    setAlwaysAllowAction,
    resetToDefaults
  }
})
