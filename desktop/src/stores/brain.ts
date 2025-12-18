import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { useAuthStore } from './auth'
import { useSessionsStore } from './sessions'
import { isBudgetExceededError } from '@/lib/litellmKeys'

export interface MessageMetrics {
  inputTokens: number
  outputTokens: number
  totalTokens: number
  cost?: number
  duration?: number
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
  result?: string
  status: 'running' | 'completed' | 'error'
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
  metrics?: MessageMetrics
  isStreaming?: boolean
  toolCalls?: ToolCall[]
  reasoning?: string[]
  isReasoningActive?: boolean
}

export interface SessionMetrics {
  totalTokens: number
  totalCost: number
  messageCount: number
  startTime: number
}

export interface LifetimeMetrics {
  totalTokens: number
  totalCost: number
  totalMessages: number
  totalSessions: number
}

// localStorage keys
const SESSION_METRICS_KEY = 'godoty_session_metrics'
const LIFETIME_METRICS_KEY = 'godoty_lifetime_metrics'

export interface PendingConfirmation {
  id: string
  action_type: 'write_file' | 'set_setting' | 'create_node' | 'delete_node' | 'delete_file'
  description: string
  details: {
    path?: string
    content?: string
    original_content?: string
    setting_path?: string
    value?: unknown
    node_name?: string
    node_type?: string
    node_path?: string
  }
}

export const useBrainStore = defineStore('brain', () => {
  const authStore = useAuthStore()
  const sessionsStore = useSessionsStore()

  const connected = ref(false)
  const godotConnected = ref(false)
  const brainReady = ref(false)  // Track if brain sidecar is responding
  const messages = ref<Message[]>([])
  const isProcessing = ref(false)
  const tokenCount = ref(0)
  const pendingConfirmation = ref<PendingConfirmation | null>(null)
  const error = ref<string | null>(null)
  const brainUrl = ref('ws://127.0.0.1:8000/ws/tauri')
  const startupStatus = ref('Initializing...')  // Status text for splash screen
  const budgetExceeded = ref(false)  // Track if user ran out of credits
  const showPurchasePrompt = ref(false)  // Show purchase credits dialog
  const toast = ref<{ message: string; type: 'success' | 'error' | 'info' } | null>(null)  // Toast notification

  // Knowledge Base State
  const knowledgeStatus = ref<{
    isIndexed: boolean
    isIndexing: boolean
    version: string
    documentCount: number
    progress?: {
      current: number
      total: number
      phase?: 'fetching' | 'embedding'
    }
  }>({
    isIndexed: false,
    isIndexing: false,
    version: '4.5',
    documentCount: 0
  })

  // Streaming state
  const streamingMessageId = ref<string | null>(null)

  // Session metrics (per chat session)
  const sessionMetrics = ref<SessionMetrics>(loadSessionMetrics())

  // Lifetime metrics (persisted across all sessions)
  const lifetimeMetrics = ref<LifetimeMetrics>(loadLifetimeMetrics())

  // Computed session stats
  const sessionDuration = computed(() => {
    if (!sessionMetrics.value.startTime) return 0
    return Math.floor((Date.now() - sessionMetrics.value.startTime) / 1000)
  })

  const knowledgeStatusText = computed(() => {
    if (knowledgeStatus.value.isIndexing) {
      if (knowledgeStatus.value.progress) {
        const { current, total, phase } = knowledgeStatus.value.progress
        const percent = Math.round((current / total) * 100)
        return `${phase === 'embedding' ? 'Embedding' : 'Fetching'} ${percent}%`
      }
      return 'Indexing...'
    }
    if (knowledgeStatus.value.isIndexed) {
      return 'Docs Ready'
    }
    return 'Docs Not Loaded'
  })

  // Load metrics from localStorage
  function loadSessionMetrics(): SessionMetrics {
    try {
      const stored = localStorage.getItem(SESSION_METRICS_KEY)
      if (stored) return JSON.parse(stored)
    } catch (e) {
      console.warn('Failed to load session metrics:', e)
    }
    return { totalTokens: 0, totalCost: 0, messageCount: 0, startTime: Date.now() }
  }

  function loadLifetimeMetrics(): LifetimeMetrics {
    try {
      const stored = localStorage.getItem(LIFETIME_METRICS_KEY)
      if (stored) return JSON.parse(stored)
    } catch (e) {
      console.warn('Failed to load lifetime metrics:', e)
    }
    return { totalTokens: 0, totalCost: 0, totalMessages: 0, totalSessions: 0 }
  }

  function saveSessionMetrics() {
    try {
      localStorage.setItem(SESSION_METRICS_KEY, JSON.stringify(sessionMetrics.value))
    } catch (e) {
      console.warn('Failed to save session metrics:', e)
    }
  }

  function saveLifetimeMetrics() {
    try {
      localStorage.setItem(LIFETIME_METRICS_KEY, JSON.stringify(lifetimeMetrics.value))
    } catch (e) {
      console.warn('Failed to save lifetime metrics:', e)
    }
  }

  function resetSessionMetrics() {
    sessionMetrics.value = { totalTokens: 0, totalCost: 0, messageCount: 0, startTime: Date.now() }
    lifetimeMetrics.value.totalSessions++
    saveSessionMetrics()
    saveLifetimeMetrics()
  }

  let ws: WebSocket | null = null
  let pendingRequests: Map<string | number, { resolve: (value: unknown) => void; reject: (error: Error) => void }> = new Map()
  let requestId = 1

  const projectInfo = ref<{
    name: string
    path: string
    godotVersion: string
  } | null>(null)

  /**
   * Check if the brain sidecar is ready and responding
   */
  async function checkBrainHealth(): Promise<boolean> {
    try {
      const ready = await invoke<boolean>('is_brain_ready')
      brainReady.value = ready
      return ready
    } catch {
      brainReady.value = false
      return false
    }
  }

  async function startBrain() {
    try {
      startupStatus.value = 'Starting brain sidecar...'
      await invoke('start_brain')

      // Poll for brain readiness instead of arbitrary timeout
      startupStatus.value = 'Waiting for brain to initialize...'
      let ready = false
      for (let i = 0; i < 30; i++) {
        ready = await checkBrainHealth()
        if (ready) break
        await new Promise(resolve => setTimeout(resolve, 200))
      }

      if (!ready) {
        error.value = 'Brain failed to start within timeout'
        return
      }

      startupStatus.value = 'Connecting to brain...'
      brainReady.value = true
      connectWebSocket()
    } catch (e) {
      error.value = `Failed to start brain: ${(e as Error).message}`
    }
  }

  async function stopBrain() {
    try {
      disconnectWebSocket()
      await invoke('stop_brain')
    } catch (e) {
      error.value = `Failed to stop brain: ${(e as Error).message}`
    }
  }

  function connectWebSocket() {
    if (ws?.readyState === WebSocket.OPEN) return

    ws = new WebSocket(brainUrl.value)
    console.log('[Brain] Connecting to WebSocket at', brainUrl.value)

    ws.onopen = async () => {
      console.log('[Brain] WebSocket connected')
      connected.value = true
      error.value = null

      // Initialize sessions store with sendRequest function
      sessionsStore.setSendRequest(sendRequest)

      // Send hello handshake and handle response
      try {
        const response = await sendRequest('hello', {
          client: 'tauri',
          protocol_version: '0.2',
        }) as {
          godot_connected?: boolean
          project?: typeof projectInfo.value
          sessions?: Array<{
            id: string
            title: string
            created_at: string
            updated_at: string
            message_count: number
          }>
          active_session_id?: string
        }

        // If Godot is already connected, set the project info from hello response
        if (response.godot_connected && response.project) {
          console.log('[Brain] Godot already connected on hello:', response.project)
          godotConnected.value = true
          projectInfo.value = response.project
        } else {
          // Fallback: Explicitly check status to be sure
          // This handles cases where Godot might be connected but hello response missed it (race condition)
          // or if notification was missed.
          const status = await sendRequest('get_status') as { godot_connected: boolean; project?: typeof projectInfo.value }
          if (status.godot_connected && status.project) {
            console.log('[Brain] Godot status sync:', status.project)
            godotConnected.value = true
            projectInfo.value = status.project
          }
        }

        // Initialize sessions from hello response
        if (response.sessions) {
          console.log('[Brain] Initializing sessions:', response.sessions.length)
          sessionsStore.initFromHelloResponse({
            sessions: response.sessions,
            active_session_id: response.active_session_id,
          })
        }
      } catch (e) {
        console.error('[Brain] Handshake/Status failed:', e)
      }
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleMessage(data)
      } catch (e) {
        console.error('Failed to parse message:', e)
      }
    }

    ws.onclose = () => {
      console.log('[Brain] WebSocket disconnected')
      connected.value = false
      // Attempt reconnection after 3 seconds
      setTimeout(() => {
        if (!connected.value) connectWebSocket()
      }, 3000)
    }

    ws.onerror = (e) => {
      error.value = 'WebSocket error'
      console.error('WebSocket error:', e)
    }
  }

  function disconnectWebSocket() {
    // Reject all pending requests to prevent memory leaks
    for (const [_id, { reject }] of pendingRequests.entries()) {
      reject(new Error('WebSocket disconnected'))
    }
    pendingRequests.clear()

    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
  }

  function handleMessage(data: Record<string, unknown>) {
    // Handle response to our request
    if (data.id !== undefined && (data.result !== undefined || data.error !== undefined)) {
      const pending = pendingRequests.get(data.id as string | number)
      if (pending) {
        pendingRequests.delete(data.id as string | number)
        if (data.error) {
          pending.reject(new Error((data.error as { message: string }).message))
        } else {
          pending.resolve(data.result)
        }
      }
      return
    }

    // Handle incoming requests/notifications from brain
    if (data.method) {
      switch (data.method) {
        case 'confirmation_request':
          handleConfirmationRequest(data.params as PendingConfirmation)
          break
        case 'godot_connected':
          console.log('[Brain] Godot connected:', data.params)
          godotConnected.value = true
          projectInfo.value = (data.params as { project: typeof projectInfo.value }).project
          break
        case 'godot_disconnected':
          console.log('[Brain] Godot disconnected')
          godotConnected.value = false
          projectInfo.value = null
          break
        case 'assistant_message':
          addMessage('assistant', (data.params as { content: string }).content)
          break
        case 'token_update':
          tokenCount.value = (data.params as { total: number }).total
          break
        case 'stream_chunk':
          // Append streaming content to the current streaming message
          if (streamingMessageId.value) {
            const msg = messages.value.find(m => m.id === streamingMessageId.value)
            if (msg) {
              msg.content += (data.params as { content: string }).content
            }
          }
          break
        case 'stream_tool_call':
          // Handle tool call events
          if (streamingMessageId.value) {
            const msg = messages.value.find(m => m.id === streamingMessageId.value)
            if (msg) {
              const params = data.params as { status: string; tool: ToolCall }
              if (!msg.toolCalls) msg.toolCalls = []

              if (params.status === 'started') {
                // Add new tool call
                msg.toolCalls.push({
                  id: params.tool.id,
                  name: params.tool.name,
                  arguments: params.tool.arguments || {},
                  status: 'running',
                })
              } else if (params.status === 'completed') {
                // Update existing tool call
                const tc = msg.toolCalls.find(t => t.id === params.tool.id)
                if (tc) {
                  tc.status = 'completed'
                  tc.result = params.tool.result
                }
              }
            }
          }
          break
        case 'stream_reasoning':
          // Handle reasoning/thinking events
          if (streamingMessageId.value) {
            const msg = messages.value.find(m => m.id === streamingMessageId.value)
            if (msg) {
              const params = data.params as { status: string; content?: string }
              if (!msg.reasoning) msg.reasoning = []

              if (params.status === 'started') {
                msg.isReasoningActive = true
              } else if (params.status === 'step' && params.content) {
                msg.reasoning.push(params.content)
              } else if (params.status === 'completed') {
                msg.isReasoningActive = false
              }
            }
          }
          break
        case 'stream_complete':
          // Finalize streaming message with metrics
          if (streamingMessageId.value) {
            const msg = messages.value.find(m => m.id === streamingMessageId.value)
            if (msg) {
              msg.isStreaming = false
              msg.isReasoningActive = false
              const params = data.params as {
                metrics?: Record<string, unknown>
                session_id?: string
                tool_calls?: ToolCall[]
                reasoning?: string[]
              }

              // Set final tool calls and reasoning if provided
              if (params.tool_calls && params.tool_calls.length > 0) {
                msg.toolCalls = params.tool_calls
              }
              if (params.reasoning && params.reasoning.length > 0) {
                msg.reasoning = params.reasoning
              }

              if (params.metrics) {
                msg.metrics = {
                  inputTokens: (params.metrics.input_tokens as number) || 0,
                  outputTokens: (params.metrics.output_tokens as number) || 0,
                  totalTokens: (params.metrics.total_tokens as number) || 0,
                  cost: (params.metrics.request_cost as number) || 0,
                }
                // Update session metrics
                sessionMetrics.value.totalTokens += msg.metrics.totalTokens
                sessionMetrics.value.totalCost += msg.metrics.cost || 0
                sessionMetrics.value.messageCount++
                saveSessionMetrics()

                // Update lifetime metrics
                lifetimeMetrics.value.totalTokens += msg.metrics.totalTokens
                lifetimeMetrics.value.totalCost += msg.metrics.cost || 0
                lifetimeMetrics.value.totalMessages++
                saveLifetimeMetrics()
              }

              // Update active session ID if provided
              if (params.session_id && sessionsStore.activeSessionId !== params.session_id) {
                sessionsStore.activeSessionId = params.session_id
                sessionsStore.persistActiveSession()
              }
            }
            streamingMessageId.value = null
          }
          break
        case 'session_updated':
          // Handle session update notification (new session or title change)
          {
            const params = data.params as {
              session: {
                id: string
                title: string
                created_at: string
                updated_at: string
                message_count: number
                total_tokens?: number
                total_cost?: number
              }
              is_new: boolean
            }

            const sessionData = {
              id: params.session.id,
              title: params.session.title,
              createdAt: new Date(params.session.created_at),
              updatedAt: new Date(params.session.updated_at),
              messageCount: params.session.message_count,
              totalTokens: params.session.total_tokens || 0,
              totalCost: params.session.total_cost || 0,
            }

            if (params.is_new) {
              // Add new session to the top of the list
              sessionsStore.sessions.unshift(sessionData)
              sessionsStore.activeSessionId = sessionData.id
              sessionsStore.persistActiveSession()
            } else {
              // Update existing session
              const existing = sessionsStore.sessions.find(s => s.id === sessionData.id)
              if (existing) {
                existing.title = sessionData.title
                existing.updatedAt = sessionData.updatedAt
                existing.messageCount = sessionData.messageCount
                existing.totalTokens = sessionData.totalTokens
                existing.totalCost = sessionData.totalCost
              }
            }
          }
          break
      }
    }

    // Notification handlers
    if (data.method === 'knowledge_status_update') {
      const params = data.params as { status: string; version: string; error?: string; document_count?: number }
      console.log('[Brain] Knowledge status update:', params)

      knowledgeStatus.value.version = params.version

      if (params.status === 'indexing') {
        knowledgeStatus.value.isIndexing = true
      } else if (params.status === 'loaded') {
        knowledgeStatus.value.isIndexing = false
        knowledgeStatus.value.isIndexed = true
        if (params.document_count !== undefined) {
          knowledgeStatus.value.documentCount = params.document_count
        }
        showToast(`Godot ${params.version} documentation indexed successfully`, 'success')
      } else if (params.status === 'error') {
        knowledgeStatus.value.isIndexing = false
        showToast(`Indexing failed: ${params.error}`, 'error')
      }
    }

    // Progress updates
    if (data.method === 'knowledge_indexing_progress') {
      const params = data.params as { current: number; total: number; version: string; phase?: 'fetching' | 'embedding' }
      if (knowledgeStatus.value.version === params.version) {
        knowledgeStatus.value.isIndexing = true
        knowledgeStatus.value.progress = {
          current: params.current,
          total: params.total,
          phase: params.phase || 'fetching'
        }
      }
    }
  }




  function sendRequest(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        reject(new Error('WebSocket not connected'))
        return
      }

      const id = requestId++
      pendingRequests.set(id, { resolve, reject })

      ws.send(JSON.stringify({
        jsonrpc: '2.0',
        method,
        params,
        id,
      }))

      // Timeout after 5 minutes
      setTimeout(() => {
        if (pendingRequests.has(id)) {
          pendingRequests.delete(id)
          reject(new Error('Request timeout'))
        }
      }, 300000)
    })
  }

  function addMessage(role: Message['role'], content: string, options?: { isStreaming?: boolean; metrics?: MessageMetrics }): string {
    const id = crypto.randomUUID()
    messages.value.push({
      id,
      role,
      content,
      timestamp: new Date(),
      isStreaming: options?.isStreaming,
      metrics: options?.metrics,
    })
    return id
  }

  async function sendUserMessage(text: string) {
    if (!text.trim() || isProcessing.value) return

    addMessage('user', text)
    isProcessing.value = true
    error.value = null
    budgetExceeded.value = false

    // Create streaming placeholder message for assistant response
    const assistantMsgId = addMessage('assistant', '', { isStreaming: true })
    streamingMessageId.value = assistantMsgId

    try {
      // Ensure we have a valid virtual key before making requests
      if (authStore.isAuthenticated && !authStore.hasValidKey) {
        await authStore.ensureVirtualKey()
      }

      const response = await sendRequest('user_message', {
        text,
        // Use virtual key instead of raw JWT for secure LiteLLM access
        authorization: authStore.virtualKey ? `Bearer ${authStore.virtualKey}` : undefined,
        // Include selected model for the brain to use
        model: authStore.selectedModel,
        // Include session ID for conversation continuity
        session_id: sessionsStore.activeSessionId,
      }) as { text: string; metrics?: Record<string, unknown>; session_id?: string }

      // Response is complete - stream_complete handler already updated the message
      // Just update token count from response if available
      if (response.metrics?.session_total_tokens) {
        tokenCount.value = response.metrics.session_total_tokens as number
      }

      // Refresh credit balance after each message
      if (authStore.isAuthenticated) {
        authStore.refreshCreditBalance()
      }
    } catch (e) {
      const err = e as Error
      error.value = err.message

      // Remove the streaming message on error
      const msgIndex = messages.value.findIndex(m => m.id === assistantMsgId)
      if (msgIndex >= 0) {
        messages.value.splice(msgIndex, 1)
      }
      streamingMessageId.value = null

      // Check if this is a budget exceeded error
      if (isBudgetExceededError(err) || err.message.includes('Insufficient credits')) {
        budgetExceeded.value = true
        showPurchasePrompt.value = true
        addMessage('system', '⚠️ You\'ve run out of credits. Please purchase more credits to continue using Godoty.')
      } else {
        addMessage('system', `Error: ${error.value}`)
      }
    } finally {
      isProcessing.value = false
    }
  }

  function handleConfirmationRequest(data: PendingConfirmation) {
    pendingConfirmation.value = data
  }

  async function respondToConfirmation(approved: boolean, modifiedContent?: string) {
    if (!pendingConfirmation.value) return

    try {
      await sendRequest('confirmation_response', {
        confirmation_id: pendingConfirmation.value.id,
        approved,
        modified_content: modifiedContent,
      })
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      pendingConfirmation.value = null
    }
  }

  async function clearMessages() {
    // Clear messages and reset active session
    // A new session will be created when user sends the next message
    sessionsStore.activeSessionId = null
    sessionsStore.clearPersistedActiveSession()
    messages.value = []
    resetSessionMetrics()
  }

  async function loadSessionMessages(sessionId: string): Promise<void> {
    isProcessing.value = true
    error.value = null

    try {
      const history = await sessionsStore.getSessionHistory(sessionId)

      messages.value = history.map((msg, index) => ({
        id: `history-${sessionId}-${index}`,
        role: msg.role as 'user' | 'assistant' | 'system',
        content: msg.content,
        timestamp: msg.created_at ? new Date(msg.created_at) : new Date(),
      }))

      await sessionsStore.switchSession(sessionId)

      const session = sessionsStore.sessions.find(s => s.id === sessionId)
      if (session) {
        sessionMetrics.value = {
          totalTokens: session.totalTokens,
          totalCost: session.totalCost,
          messageCount: session.messageCount,
          startTime: session.createdAt.getTime(),
        }
        saveSessionMetrics()
      }
    } catch (e) {
      error.value = `Failed to load session: ${(e as Error).message}`
    } finally {
      isProcessing.value = false
    }
  }

  function showToast(message: string, type: 'success' | 'error' | 'info' = 'info') {
    toast.value = { message, type }
    // Auto-hide after 5 seconds
    setTimeout(() => {
      if (toast.value?.message === message) {
        toast.value = null
      }
    }, 5000)
  }

  function hideToast() {
    toast.value = null
  }

  function dismissPurchasePrompt() {
    showPurchasePrompt.value = false
  }

  // Called after successful credit purchase
  function onCreditsPurchased() {
    budgetExceeded.value = false
    showPurchasePrompt.value = false
    showToast('Credits added successfully! You can continue using Godoty.', 'success')
    // Refresh balance
    if (authStore.isAuthenticated) {
      authStore.refreshCreditBalance()
    }
  }



  async function reindexKnowledge() {
    try {
      showToast('Started reindexing documentation...', 'info')
      await sendRequest('admin_reindex_knowledge')
      // Status updates will come via notifications
    } catch (e) {
      showToast(`Failed to start reindexing: ${(e as Error).message}`, 'error')
    }
  }

  async function checkKnowledgeStatus() {
    try {
      const status = await sendRequest('get_knowledge_status') as {
        version: string
        is_indexed: boolean
        is_indexing: boolean
        document_count: number
      }

      knowledgeStatus.value = {
        version: status.version,
        isIndexed: status.is_indexed,
        isIndexing: status.is_indexing,
        documentCount: status.document_count
      }
    } catch (e) {
      console.warn('Failed to check knowledge status:', e)
    }
  }

  async function listIndexedVersions(): Promise<{ versions: Array<{ version: string; document_count: number; size_bytes: number }> }> {
    try {
      return await sendRequest('list_indexed_versions') as { versions: Array<{ version: string; document_count: number; size_bytes: number }> }
    } catch (e) {
      console.warn('Failed to list indexed versions:', e)
      return { versions: [] }
    }
  }

  async function deleteIndexedVersion(version: string): Promise<void> {
    await sendRequest('delete_indexed_version', { version })
  }

  async function reindexVersion(version: string): Promise<void> {
    await sendRequest('reindex_version', { version })
  }

  return {
    connected,
    godotConnected,
    brainReady,
    startupStatus,
    messages,
    isProcessing,
    tokenCount,
    knowledgeStatus,
    pendingConfirmation,
    error,
    projectInfo,
    budgetExceeded,
    showPurchasePrompt,
    toast,
    sessionMetrics,
    lifetimeMetrics,
    sessionDuration,
    knowledgeStatusText,
    startBrain,
    stopBrain,
    checkBrainHealth,
    connectWebSocket,
    disconnectWebSocket,
    sendUserMessage,
    respondToConfirmation,
    clearMessages,
    loadSessionMessages,
    resetSessionMetrics,
    showToast,
    hideToast,
    dismissPurchasePrompt,
    onCreditsPurchased,
    reindexKnowledge,
    checkKnowledgeStatus,
    listIndexedVersions,
    deleteIndexedVersion,
    reindexVersion,
  }
})
