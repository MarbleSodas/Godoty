import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { supabase } from '@/lib/supabase'
import {
  generateVirtualKey,
  fetchAvailableModels,
  getCachedVirtualKey,
  clearVirtualKey,
  isKeyExpired,
  getSelectedModel,
  setSelectedModel as saveSelectedModel,
  formatCredits,
  PRICING_URL,
  type VirtualKeyInfo,
  type ModelId,
  type ModelInfo,
} from '@/lib/litellmKeys'
import type { User, Session } from '@supabase/supabase-js'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const session = ref<Session | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Virtual key state (includes balance info from LiteLLM)
  const virtualKeyInfo = ref<VirtualKeyInfo | null>(null)
  const keyLoading = ref(false)
  const keyError = ref<string | null>(null)

  // Initialization state
  const initialized = ref(false)
  const initPromise = ref<Promise<void> | null>(null)

  // Email confirmation state
  const confirmationPending = ref(false)
  const confirmationEmail = ref<string | null>(null)

  // Model selection state
  const selectedModel = ref<ModelId>(getSelectedModel())
  const availableModels = ref<ModelInfo[]>([])
  const modelsLoading = ref(false)

  const isAuthenticated = computed(() => !!session.value)
  const accessToken = computed(() => session.value?.access_token ?? null)

  // Virtual key for LiteLLM API calls
  const virtualKey = computed(() => virtualKeyInfo.value?.apiKey ?? null)

  // Key display state
  const showFullKey = ref(false)

  // Masked key for display (shows last 8 characters)
  const maskedKey = computed(() => {
    const key = virtualKey.value
    if (!key) return null
    if (showFullKey.value) return key
    if (key.length <= 8) return key
    return '••••••••' + key.slice(-8)
  })

  // Credit balance info from virtualKeyInfo (4 decimal precision strings)
  const remainingCredits = computed(() => virtualKeyInfo.value?.remainingBudget ?? '0.0000')
  const maxCredits = computed(() => virtualKeyInfo.value?.maxBudget ?? '0.0000')
  const usedCredits = computed(() => virtualKeyInfo.value?.spend ?? '0.0000')
  const hasValidKey = computed(() =>
    virtualKeyInfo.value !== null && !isKeyExpired(virtualKeyInfo.value)
  )

  // Formatted credit display
  const formattedRemainingCredits = computed(() => formatCredits(remainingCredits.value))
  const formattedMaxCredits = computed(() => formatCredits(maxCredits.value))
  const formattedUsedCredits = computed(() => formatCredits(usedCredits.value))

  // Check if user has sufficient credits (more than $0.0001)
  const hasSufficientCredits = computed(() => parseFloat(remainingCredits.value) > 0.0001)

  /**
   * Toggle key visibility
   */
  function toggleKeyVisibility(): void {
    showFullKey.value = !showFullKey.value
  }

  /**
   * Force regenerate virtual key (clears cache first)
   */
  async function regenerateVirtualKey(): Promise<void> {
    if (!accessToken.value) {
      keyError.value = 'Not authenticated'
      return
    }

    // Clear cached key to force regeneration
    clearVirtualKey()
    virtualKeyInfo.value = null

    keyLoading.value = true
    keyError.value = null
    try {
      const keyInfo = await generateVirtualKey(accessToken.value, true)
      virtualKeyInfo.value = keyInfo
    } catch (e) {
      keyError.value = (e as Error).message
      console.error('Failed to regenerate virtual key:', e)
    } finally {
      keyLoading.value = false
    }
  }

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
   * Refresh the credit balance by fetching fresh key info from LiteLLM
   * The generate-litellm-key endpoint returns current balance from LiteLLM
   */
  async function refreshCreditBalance(): Promise<void> {
    if (!accessToken.value) return

    try {
      // Force fetch fresh key info (bypassing cache) to get updated balance
      const keyInfo = await generateVirtualKey(accessToken.value, true)
      virtualKeyInfo.value = keyInfo
    } catch (e) {
      console.error('Failed to refresh credit balance:', e)
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
        // Set up auth state change listener following Supabase docs
        // Handle different event types appropriately
        supabase.auth.onAuthStateChange(async (event, newSession) => {
          console.log('[Auth] Event:', event)

          if (event === 'INITIAL_SESSION') {
            // Initial session load from storage - just update state
            // Key will be fetched below in getSession() handling
            session.value = newSession
            user.value = newSession?.user ?? null
          } else if (event === 'SIGNED_IN') {
            // User just signed in - get their virtual key
            session.value = newSession
            user.value = newSession?.user ?? null
            if (newSession?.access_token) {
              await ensureVirtualKey()
              await refreshModels()
            }
          } else if (event === 'SIGNED_OUT') {
            // User signed out - clear everything
            session.value = null
            user.value = null
            virtualKeyInfo.value = null
            availableModels.value = []
            clearVirtualKey()
          } else if (event === 'TOKEN_REFRESHED') {
            // Token refreshed - just update session, DON'T regenerate key
            session.value = newSession
          }
          // Ignore USER_UPDATED, PASSWORD_RECOVERY for key management
        })

        // Get initial session and fetch key if needed
        const { data } = await supabase.auth.getSession()
        session.value = data.session
        user.value = data.session?.user ?? null

        if (data.session?.access_token) {
          await ensureVirtualKey()
          await refreshModels()
        }
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

  async function signUpWithEmail(email: string, password: string): Promise<{ confirmationRequired: boolean }> {
    loading.value = true
    error.value = null
    confirmationPending.value = false
    confirmationEmail.value = null

    try {
      // Use the desktop callback URL so email confirmation links redirect back to the desktop app
      const emailRedirectUrl = 'https://godoty.app/auth/desktop-callback'

      const { data, error: authError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          emailRedirectTo: emailRedirectUrl,
        },
      })
      if (authError) throw authError

      session.value = data.session
      user.value = data.user

      // If session is null but user exists, email confirmation is pending
      // Supabase returns user data but no session when confirmation is required
      if (data.user && !data.session) {
        confirmationPending.value = true
        confirmationEmail.value = email
        return { confirmationRequired: true }
      }

      return { confirmationRequired: false }
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
      // 3. The web callback at godoty.app/auth/desktop-callback will redirect to godoty://auth/callback
      const redirectUrl = 'https://godoty.app/auth/desktop-callback'

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
      clearVirtualKey()
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  }

  /**
   * Open the pricing page in browser to purchase credits
   */
  async function openPricingPage(): Promise<void> {
    try {
      const { open } = await import('@tauri-apps/plugin-shell')
      await open(PRICING_URL)
    } catch (e) {
      console.error('Failed to open pricing page:', e)
      // Fallback: copy URL to clipboard or show it
      window.open(PRICING_URL, '_blank')
    }
  }

  /**
   * Handle deep link authentication callback
   * @param url The deep link URL (e.g. godoty://auth/callback?access_token=...&refresh_token=...)
   */
  async function handleDeepLink(url: string) {
    loading.value = true
    try {
      // Parse the URL to get tokens or code
      // Note: Don't log the full URL as it contains sensitive tokens
      const urlObj = new URL(url)
      const accessToken = urlObj.searchParams.get('access_token')
      const refreshToken = urlObj.searchParams.get('refresh_token')
      const code = urlObj.searchParams.get('code')
      const errorDescription = urlObj.searchParams.get('error_description')

      if (errorDescription) {
        throw new Error(errorDescription)
      }

      // If we have access_token and refresh_token, use setSession directly
      // This is the preferred path - the web callback already exchanged the code
      if (accessToken && refreshToken) {
        const { data, error: authError } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken,
        })
        if (authError) throw authError

        session.value = data.session
        user.value = data.user

        if (data.session) {
          await ensureVirtualKey()
          await refreshModels()
        }
      } else if (code) {
        // Fallback: try to exchange code for session
        // This may fail if code_verifier is not available
        const { data, error: authError } = await supabase.auth.exchangeCodeForSession(code)
        if (authError) throw authError

        session.value = data.session
        user.value = data.user

        if (data.session) {
          await ensureVirtualKey()
          await refreshModels()
        }
      }
    } catch (e) {
      error.value = (e as Error).message
      console.error('Deep link auth error:', e)
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
    confirmationPending,
    confirmationEmail,
    virtualKeyInfo,
    keyLoading,
    keyError,
    selectedModel,
    showFullKey,

    // Computed
    isAuthenticated,
    accessToken,
    virtualKey,
    maskedKey,
    remainingCredits,
    maxCredits,
    usedCredits,
    hasValidKey,
    availableModels,
    modelsLoading,
    formattedRemainingCredits,
    formattedMaxCredits,
    formattedUsedCredits,
    hasSufficientCredits,

    // Actions
    initialize,
    signInWithEmail,
    signUpWithEmail,
    signInWithOAuth,
    signOut,
    ensureVirtualKey,
    regenerateVirtualKey,
    refreshCreditBalance,
    refreshModels,
    setSelectedModelId,
    toggleKeyVisibility,
    openPricingPage,
    handleDeepLink,
  }
})
