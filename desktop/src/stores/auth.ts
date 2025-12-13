import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { supabase } from '@/lib/supabase'
import {
  generateVirtualKey,
  fetchCreditBalance,
  fetchAvailableModels,
  getCachedVirtualKey,
  clearVirtualKey,
  isKeyExpired,
  getSelectedModel,
  setSelectedModel as saveSelectedModel,
  type VirtualKeyInfo,
  type CreditBalance,
  type ModelId,
  type ModelInfo,
} from '@/lib/litellmKeys'
import type { User, Session } from '@supabase/supabase-js'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const session = ref<Session | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Virtual key state
  const virtualKeyInfo = ref<VirtualKeyInfo | null>(null)
  const creditBalance = ref<CreditBalance | null>(null)
  const keyLoading = ref(false)
  const keyError = ref<string | null>(null)

  // Initialization state
  const initialized = ref(false)
  const initPromise = ref<Promise<void> | null>(null)

  // Model selection state
  const selectedModel = ref<ModelId>(getSelectedModel())
  const availableModels = ref<ModelInfo[]>([])
  const modelsLoading = ref(false)

  const isAuthenticated = computed(() => !!session.value)
  const accessToken = computed(() => session.value?.access_token ?? null)

  // Virtual key for LiteLLM API calls
  const virtualKey = computed(() => virtualKeyInfo.value?.apiKey ?? null)

  // Credit balance info
  const remainingCredits = computed(() => creditBalance.value?.remainingBudget ?? 0)
  const maxCredits = computed(() => creditBalance.value?.maxBudget ?? 0)
  const usedCredits = computed(() => creditBalance.value?.usedBudget ?? 0)
  const hasValidKey = computed(() =>
    virtualKeyInfo.value !== null && !isKeyExpired(virtualKeyInfo.value)
  )

  /**
   * Fetch or generate a virtual key for the current user
   */
  async function ensureVirtualKey(): Promise<void> {
    if (!accessToken.value) {
      keyError.value = 'Not authenticated'
      return
    }

    // Check if we have a valid cached key
    const cached = getCachedVirtualKey()
    if (cached && !isKeyExpired(cached)) {
      virtualKeyInfo.value = cached
      return
    }

    keyLoading.value = true
    keyError.value = null
    try {
      const keyInfo = await generateVirtualKey(accessToken.value)
      virtualKeyInfo.value = keyInfo
    } catch (e) {
      keyError.value = (e as Error).message
      console.error('Failed to get virtual key:', e)
    } finally {
      keyLoading.value = false
    }
  }

  /**
   * Refresh the credit balance from the server
   */
  async function refreshCreditBalance(): Promise<void> {
    if (!accessToken.value) return

    try {
      const balance = await fetchCreditBalance(accessToken.value)
      creditBalance.value = balance
    } catch (e) {
      console.error('Failed to fetch credit balance:', e)
    }
  }

  /**
   * Fetch available models from LiteLLM proxy
   */
  async function refreshModels(): Promise<void> {
    modelsLoading.value = true
    try {
      const models = await fetchAvailableModels(virtualKey.value ?? undefined)
      availableModels.value = models
    } catch (e) {
      console.error('Failed to fetch available models:', e)
      // Keep fallback models on error
    } finally {
      modelsLoading.value = false
    }
  }

  /**
   * Update the selected model
   */
  function setSelectedModelId(modelId: ModelId): void {
    selectedModel.value = modelId
    saveSelectedModel(modelId)
  }

  async function initialize() {
    // If already initialized, return immediately
    if (initialized.value) {
      return
    }

    // If initialization is in progress, wait for it
    if (initPromise.value) {
      return initPromise.value
    }

    // Start initialization
    const doInit = async () => {
      loading.value = true
      try {
        const { data: { session: currentSession } } = await supabase.auth.getSession()
        session.value = currentSession
        user.value = currentSession?.user ?? null

        // If user is logged in, ensure they have a virtual key
        if (currentSession?.access_token) {
          await ensureVirtualKey()
          await refreshCreditBalance()
          // Fetch available models using the virtual key
          await refreshModels()
        }

        // Listen for auth changes
        supabase.auth.onAuthStateChange(async (_event, newSession) => {
          session.value = newSession
          user.value = newSession?.user ?? null

          // When user logs in, get their virtual key and fetch models
          if (newSession?.access_token) {
            await ensureVirtualKey()
            await refreshCreditBalance()
            // Fetch available models using the virtual key
            await refreshModels()
          } else {
            // User logged out, clear key info and models
            virtualKeyInfo.value = null
            creditBalance.value = null
            availableModels.value = []
            clearVirtualKey()
          }
        })
      } catch (e) {
        error.value = (e as Error).message
      } finally {
        loading.value = false
        initialized.value = true
      }
    }

    initPromise.value = doInit()
    return initPromise.value
  }

  async function signInWithEmail(email: string, password: string) {
    loading.value = true
    error.value = null
    try {
      const { data, error: authError } = await supabase.auth.signInWithPassword({
        email,
        password,
      })
      if (authError) throw authError
      session.value = data.session
      user.value = data.user
    } catch (e) {
      error.value = (e as Error).message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function signUpWithEmail(email: string, password: string) {
    loading.value = true
    error.value = null
    try {
      const { data, error: authError } = await supabase.auth.signUp({
        email,
        password,
      })
      if (authError) throw authError
      session.value = data.session
      user.value = data.user
    } catch (e) {
      error.value = (e as Error).message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function signInWithOAuth(provider: 'github' | 'google') {
    loading.value = true
    error.value = null
    try {
      // In Tauri desktop apps, we need to:
      // 1. Get the OAuth URL with skipBrowserRedirect
      // 2. Open it in the system browser via Tauri shell plugin
      // 3. The redirect will come back to localhost:1420 which Tauri serves
      const redirectUrl = import.meta.env.DEV
        ? 'http://localhost:1420'
        : window.location.origin

      const { data, error: authError } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: redirectUrl,
          skipBrowserRedirect: true, // Don't auto-redirect, we'll handle it
        },
      })

      if (authError) throw authError

      // Open the OAuth URL in the system default browser
      // This will show the OAuth consent screen
      if (data?.url) {
        // Use Tauri's shell plugin to open URL
        const { open } = await import('@tauri-apps/plugin-shell')
        await open(data.url)
      }
    } catch (e) {
      error.value = (e as Error).message
      throw e
    } finally {
      loading.value = false
    }
  }

  async function signOut() {
    loading.value = true
    try {
      await supabase.auth.signOut()
      session.value = null
      user.value = null
      virtualKeyInfo.value = null
      creditBalance.value = null
      clearVirtualKey()
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  }

  return {
    // State
    user,
    session,
    loading,
    error,
    initialized,

    // Virtual key state
    virtualKeyInfo,
    creditBalance,
    keyLoading,
    keyError,
    selectedModel,

    // Computed
    isAuthenticated,
    accessToken,
    virtualKey,
    remainingCredits,
    maxCredits,
    usedCredits,
    hasValidKey,
    availableModels,
    modelsLoading,

    // Actions
    initialize,
    signInWithEmail,
    signUpWithEmail,
    signInWithOAuth,
    signOut,
    ensureVirtualKey,
    refreshCreditBalance,
    refreshModels,
    setSelectedModelId,
  }
})
