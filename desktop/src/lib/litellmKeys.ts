import { supabase } from '@/lib/supabase'

// Type definitions
export interface VirtualKeyInfo {
  apiKey: string
  expiresAt: string
  maxBudget: string
  spend: string
  remainingBudget: string
}

export type ModelId = string

export interface ModelInfo {
  id: ModelId
  name: string
}

export const PRICING_URL = 'https://godoty.app/pricing'

// Credit formatting - show up to 2 decimal places, remove trailing zeros
export function formatCredits(credits: string | number): string {
  const num = typeof credits === 'string' ? parseFloat(credits) : credits
  if (isNaN(num)) return '0.00'
  // Round to 2 decimal places and remove trailing zeros
  return num.toFixed(2).replace(/\.?0+$/, '')
}

// LocalStorage keys for caching
const VIRTUAL_KEY_CACHE_KEY = 'godoty_virtual_key'
const CREDIT_BALANCE_CACHE_KEY = 'godoty_credit_balance'
const RATE_LIMIT_KEY = 'godoty_rate_limit'

// Rate limiting helpers (5 calls per hour)
export function isRateLimited(): boolean {
  try {
    const data = localStorage.getItem(RATE_LIMIT_KEY)
    if (!data) return false
    const { timestamp, count } = JSON.parse(data)
    const oneHour = 60 * 60 * 1000
    if (Date.now() - timestamp > oneHour) {
      clearRateLimitState()
      return false
    }
    return count >= 5
  } catch {
    return false
  }
}

export function getRateLimitResetSeconds(): number {
  try {
    const data = localStorage.getItem(RATE_LIMIT_KEY)
    if (!data) return 0
    const { timestamp } = JSON.parse(data)
    const oneHour = 60 * 60
    const elapsed = Math.floor((Date.now() - timestamp) / 1000)
    return Math.max(0, oneHour - elapsed)
  } catch {
    return 0
  }
}

export function clearRateLimitState(): void {
  localStorage.removeItem(RATE_LIMIT_KEY)
}

function recordRateLimit(): void {
  try {
    const data = localStorage.getItem(RATE_LIMIT_KEY)
    if (!data) {
      localStorage.setItem(RATE_LIMIT_KEY, JSON.stringify({ timestamp: Date.now(), count: 1 }))
      return
    }
    const { timestamp, count } = JSON.parse(data)
    const oneHour = 60 * 60 * 1000
    if (Date.now() - timestamp > oneHour) {
      localStorage.setItem(RATE_LIMIT_KEY, JSON.stringify({ timestamp: Date.now(), count: 1 }))
    } else {
      localStorage.setItem(RATE_LIMIT_KEY, JSON.stringify({ timestamp, count: count + 1 }))
    }
  } catch (e) {
    console.warn('Failed to record rate limit:', e)
  }
}

// Cache management
export function getCachedVirtualKey(): VirtualKeyInfo | null {
  try {
    const data = localStorage.getItem(VIRTUAL_KEY_CACHE_KEY)
    if (!data) return null
    const cached = JSON.parse(data) as VirtualKeyInfo
    // Check if expired (24 hours)
    const expiresAt = new Date(cached.expiresAt)
    if (expiresAt < new Date()) {
      clearVirtualKey()
      return null
    }
    return cached
  } catch {
    return null
  }
}

function setCachedVirtualKey(keyInfo: VirtualKeyInfo): void {
  try {
    // Set expiration to 24 hours from now
    const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
    const toCache = { ...keyInfo, expiresAt }
    localStorage.setItem(VIRTUAL_KEY_CACHE_KEY, JSON.stringify(toCache))
  } catch (e) {
    console.warn('Failed to cache virtual key:', e)
  }
}

export function clearVirtualKey(): void {
  localStorage.removeItem(VIRTUAL_KEY_CACHE_KEY)
}

export function isKeyExpired(keyInfo: VirtualKeyInfo): boolean {
  const expiresAt = new Date(keyInfo.expiresAt)
  return expiresAt < new Date()
}

export function getSelectedModel(): ModelId {
  try {
    return localStorage.getItem('godoty_selected_model') || 'anthropic/claude-sonnet-4'
  } catch {
    return 'anthropic/claude-sonnet-4'
  }
}

export function setSelectedModel(modelId: ModelId): void {
  try {
    localStorage.setItem('godoty_selected_model', modelId)
  } catch (e) {
    console.warn('Failed to save selected model:', e)
  }
}

// Credit balance cache
export function updateCachedCreditBalance(data: {
  totalCredits: string
  usedCredits: string
  remainingCredits: string
}): void {
  try {
    localStorage.setItem(CREDIT_BALANCE_CACHE_KEY, JSON.stringify(data))
  } catch (e) {
    console.warn('Failed to cache credit balance:', e)
  }
}

export function clearCachedCreditBalance(): void {
  localStorage.removeItem(CREDIT_BALANCE_CACHE_KEY)
}

// Supabase edge function to generate/retrieve LiteLLM virtual key
export async function generateVirtualKey(
  accessToken: string,
  forceRegenerate: boolean = false
): Promise<VirtualKeyInfo> {
  // Check rate limit
  if (isRateLimited()) {
    throw new Error(`Rate limit exceeded. Please try again later.`)
  }

  // Check cache first if not forcing regeneration
  if (!forceRegenerate) {
    const cached = getCachedVirtualKey()
    if (cached && !isKeyExpired(cached)) {
      return cached
    }
  }

  const { data, error } = await supabase.functions.invoke('generate-litellm-key', {
    body: { force_regenerate: forceRegenerate },
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })

  if (error) {
    // Check if rate limited
    if (error.message?.includes('Rate limit') || error.message?.includes('rate limit')) {
      recordRateLimit()
      throw new Error('Rate limit exceeded (5 calls per hour). Please try again later.')
    }
    throw new Error(error.message || 'Failed to generate virtual key')
  }

  const keyInfo: VirtualKeyInfo = {
    apiKey: data.api_key,
    expiresAt: data.expires_at || new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
    maxBudget: data.max_budget?.toString() || '0.00',
    spend: data.spend?.toString() || '0.00',
    remainingBudget: data.remaining_budget?.toString() || '0.00',
  }

  // Cache the key
  setCachedVirtualKey(keyInfo)

  return keyInfo
}

// Fetch available models from LiteLLM proxy
export async function fetchAvailableModels(virtualKey?: string): Promise<ModelInfo[]> {
  const fallbackModels: ModelInfo[] = [
    { id: 'anthropic/claude-sonnet-4', name: 'Claude Sonnet 4' },
    { id: 'anthropic/claude-3-5-sonnet', name: 'Claude 3.5 Sonnet' },
  ]

  try {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (virtualKey) {
      headers['Authorization'] = `Bearer ${virtualKey}`
    }

    const response = await fetch('https://api.litellm.ai/model/info', {
      method: 'GET',
      headers,
    })

    if (!response.ok) {
      return fallbackModels
    }

    const responseData = await response.json()
    if (responseData.data && Array.isArray(responseData.data)) {
      return responseData.data.map((model: any) => ({
        id: model.id || model.model_name,
        name: model.id || model.model_name,
      }))
    }

    return fallbackModels
  } catch (e) {
    console.warn('Failed to fetch available models:', e)
    return fallbackModels
  }
}

// Fetch credit balance directly from Supabase (bypasses edge function rate limits)
export async function fetchCreditBalance(supabaseClient: typeof supabase): Promise<{
  totalCredits: string
  usedCredits: string
  remainingCredits: string
} | null> {
  try {
    const { data: userData, error: userError } = await supabaseClient.auth.getUser()
    if (userError || !userData.user) {
      return null
    }

    const { data, error } = await supabaseClient
      .from('LiteLLM_UserTable')
      .select('max_budget, spend')
      .eq('user_id', userData.user.id)
      .single()

    if (error || !data) {
      return null
    }

    const maxBudget = parseFloat(data.max_budget || '0')
    const spend = parseFloat(data.spend || '0')
    const remaining = Math.max(0, maxBudget - spend)

    return {
      totalCredits: maxBudget.toFixed(4),
      usedCredits: spend.toFixed(4),
      remainingCredits: remaining.toFixed(4),
    }
  } catch (e) {
    console.warn('Failed to fetch credit balance:', e)
    return null
  }
}
