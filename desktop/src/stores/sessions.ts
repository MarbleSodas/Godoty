import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface ChatSession {
    id: string
    title: string
    createdAt: Date
    updatedAt: Date
    messageCount: number
    totalTokens: number
    totalCost: number
}

// localStorage key for persisting active session
const ACTIVE_SESSION_KEY = 'godoty_active_session'

export const useSessionsStore = defineStore('sessions', () => {
    const sessions = ref<ChatSession[]>([])
    const activeSessionId = ref<string | null>(null)
    const isLoading = ref(false)
    const error = ref<string | null>(null)

    // Computed property for active session
    const activeSession = computed(() =>
        sessions.value.find(s => s.id === activeSessionId.value)
    )

    // WebSocket request helper - uses the brain store's sendRequest
    // This will be called from components that have access to brainStore
    let _sendRequest: ((method: string, params?: Record<string, unknown>) => Promise<unknown>) | null = null

    function setSendRequest(fn: (method: string, params?: Record<string, unknown>) => Promise<unknown>) {
        _sendRequest = fn
    }

    async function sendRequest(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
        if (!_sendRequest) {
            throw new Error('sendRequest not initialized - call setSendRequest first')
        }
        return _sendRequest(method, params)
    }

    /**
     * Initialize sessions from hello response data
     */
    function initFromHelloResponse(data: {
        sessions?: Array<{
            id: string
            title: string
            created_at: string
            updated_at: string
            message_count: number
            total_tokens?: number
            total_cost?: number
        }>
        active_session_id?: string
    }) {
        if (data.sessions) {
            sessions.value = data.sessions.map(s => ({
                id: s.id,
                title: s.title,
                createdAt: new Date(s.created_at),
                updatedAt: new Date(s.updated_at),
                messageCount: s.message_count,
                totalTokens: s.total_tokens || 0,
                totalCost: s.total_cost || 0,
            }))
        }

        // Use persisted active session if available, otherwise use server default
        const persisted = loadPersistedActiveSession()
        if (persisted && sessions.value.some(s => s.id === persisted)) {
            activeSessionId.value = persisted
        } else if (data.active_session_id) {
            activeSessionId.value = data.active_session_id
            persistActiveSession()
        }
    }

    /**
     * Load sessions from the brain server
     */
    async function loadSessions(): Promise<void> {
        if (!_sendRequest) return

        isLoading.value = true
        error.value = null

        try {
            const response = await sendRequest('list_sessions') as {
                sessions: Array<{
                    id: string
                    title: string
                    created_at: string
                    updated_at: string
                    message_count: number
                    total_tokens?: number
                    total_cost?: number
                }>
            }

            sessions.value = response.sessions.map(s => ({
                id: s.id,
                title: s.title,
                createdAt: new Date(s.created_at),
                updatedAt: new Date(s.updated_at),
                messageCount: s.message_count,
                totalTokens: s.total_tokens || 0,
                totalCost: s.total_cost || 0,
            }))
        } catch (e) {
            error.value = (e as Error).message
            console.error('[Sessions] Failed to load sessions:', e)
        } finally {
            isLoading.value = false
        }
    }

    /**
     * Create a new session and switch to it
     */
    async function createSession(title: string = 'New Chat'): Promise<ChatSession | null> {
        if (!_sendRequest) return null

        isLoading.value = true
        error.value = null

        try {
            const response = await sendRequest('create_session', { title }) as {
                session: {
                    id: string
                    title: string
                    created_at: string
                    updated_at: string
                    message_count: number
                    total_tokens?: number
                    total_cost?: number
                }
            }

            const newSession: ChatSession = {
                id: response.session.id,
                title: response.session.title,
                createdAt: new Date(response.session.created_at),
                updatedAt: new Date(response.session.updated_at),
                messageCount: response.session.message_count,
                totalTokens: response.session.total_tokens || 0,
                totalCost: response.session.total_cost || 0,
            }

            // Add to beginning of list
            sessions.value.unshift(newSession)

            // Switch to new session
            activeSessionId.value = newSession.id
            persistActiveSession()

            return newSession
        } catch (e) {
            error.value = (e as Error).message
            console.error('[Sessions] Failed to create session:', e)
            return null
        } finally {
            isLoading.value = false
        }
    }

    /**
     * Switch to a different session
     */
    async function switchSession(sessionId: string): Promise<boolean> {
        const session = sessions.value.find(s => s.id === sessionId)
        if (!session) {
            error.value = 'Session not found'
            return false
        }

        activeSessionId.value = sessionId
        persistActiveSession()
        return true
    }

    /**
     * Delete a session
     */
    async function deleteSession(sessionId: string): Promise<boolean> {
        if (!_sendRequest) return false

        isLoading.value = true
        error.value = null

        try {
            await sendRequest('delete_session', { session_id: sessionId })

            // Remove from local state
            sessions.value = sessions.value.filter(s => s.id !== sessionId)

            // If we deleted the active session, switch to the first available or clear
            if (activeSessionId.value === sessionId) {
                if (sessions.value.length > 0) {
                    activeSessionId.value = sessions.value[0].id
                    persistActiveSession()
                } else {
                    // No sessions left - clear active session
                    // A new session will be created when user sends first message
                    activeSessionId.value = null
                    clearPersistedActiveSession()
                }
            }

            return true
        } catch (e) {
            error.value = (e as Error).message
            console.error('[Sessions] Failed to delete session:', e)
            return false
        } finally {
            isLoading.value = false
        }
    }

    /**
     * Rename a session
     */
    async function renameSession(sessionId: string, title: string): Promise<boolean> {
        if (!_sendRequest) return false

        try {
            const response = await sendRequest('rename_session', {
                session_id: sessionId,
                title,
            }) as {
                session: {
                    id: string
                    title: string
                    created_at: string
                    updated_at: string
                    message_count: number
                }
            }

            // Update local state
            const session = sessions.value.find(s => s.id === sessionId)
            if (session) {
                session.title = response.session.title
                session.updatedAt = new Date(response.session.updated_at)
            }

            return true
        } catch (e) {
            error.value = (e as Error).message
            console.error('[Sessions] Failed to rename session:', e)
            return false
        }
    }

    /**
     * Get session history (chat messages)
     */
    async function getSessionHistory(sessionId: string): Promise<Array<{ role: string; content: string }>> {
        if (!_sendRequest) return []

        try {
            const response = await sendRequest('get_session_history', {
                session_id: sessionId,
            }) as {
                session_id: string
                title: string
                messages: Array<{ role: string; content: string }>
            }

            return response.messages
        } catch (e) {
            console.error('[Sessions] Failed to get session history:', e)
            return []
        }
    }

    /**
     * Update session in local state (e.g., after receiving a message)
     */
    function updateSessionLocally(sessionId: string, updates: { title?: string; messageCount?: number }) {
        const session = sessions.value.find(s => s.id === sessionId)
        if (session) {
            if (updates.title !== undefined) {
                session.title = updates.title
            }
            if (updates.messageCount !== undefined) {
                session.messageCount = updates.messageCount
            }
            session.updatedAt = new Date()

            // Move to top of list
            const index = sessions.value.indexOf(session)
            if (index > 0) {
                sessions.value.splice(index, 1)
                sessions.value.unshift(session)
            }
        }
    }

    /**
     * Persist active session ID to localStorage
     */
    function persistActiveSession() {
        if (activeSessionId.value) {
            try {
                localStorage.setItem(ACTIVE_SESSION_KEY, activeSessionId.value)
            } catch (e) {
                console.warn('[Sessions] Failed to persist active session:', e)
            }
        }
    }

    /**
     * Load active session ID from localStorage
     */
    function loadPersistedActiveSession(): string | null {
        try {
            return localStorage.getItem(ACTIVE_SESSION_KEY)
        } catch (e) {
            console.warn('[Sessions] Failed to load persisted active session:', e)
            return null
        }
    }

    /**
     * Clear persisted active session
     */
    function clearPersistedActiveSession() {
        try {
            localStorage.removeItem(ACTIVE_SESSION_KEY)
        } catch (e) {
            console.warn('[Sessions] Failed to clear persisted active session:', e)
        }
    }

    return {
        // State
        sessions,
        activeSessionId,
        isLoading,
        error,

        // Computed
        activeSession,

        // Actions
        setSendRequest,
        initFromHelloResponse,
        loadSessions,
        createSession,
        switchSession,
        deleteSession,
        renameSession,
        getSessionHistory,
        updateSessionLocally,
        persistActiveSession,
        loadPersistedActiveSession,
        clearPersistedActiveSession,
    }
})
