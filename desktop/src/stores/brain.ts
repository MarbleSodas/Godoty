import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { useAuthStore } from './auth'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
}

export interface PendingConfirmation {
  id: string
  action_type: 'write_file' | 'set_setting' | 'create_node' | 'delete_node'
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
  
  const connected = ref(false)
  const godotConnected = ref(false)
  const messages = ref<Message[]>([])
  const isProcessing = ref(false)
  const tokenCount = ref(0)
  const pendingConfirmation = ref<PendingConfirmation | null>(null)
  const error = ref<string | null>(null)
  const brainUrl = ref('ws://127.0.0.1:8000/ws/tauri')
  
  let ws: WebSocket | null = null
  let pendingRequests: Map<string | number, { resolve: (value: unknown) => void; reject: (error: Error) => void }> = new Map()
  let requestId = 1

  const projectInfo = ref<{
    name: string
    path: string
    godotVersion: string
  } | null>(null)

  async function startBrain() {
    try {
      await invoke('start_brain')
      // Wait a bit for the server to start
      await new Promise(resolve => setTimeout(resolve, 2000))
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

    ws.onopen = () => {
      connected.value = true
      error.value = null
      // Send hello handshake
      sendRequest('hello', {
        client: 'tauri',
        protocol_version: '0.2',
      })
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
          godotConnected.value = true
          projectInfo.value = (data.params as { project: typeof projectInfo.value }).project
          break
        case 'godot_disconnected':
          godotConnected.value = false
          projectInfo.value = null
          break
        case 'assistant_message':
          addMessage('assistant', (data.params as { content: string }).content)
          break
        case 'token_update':
          tokenCount.value = (data.params as { total: number }).total
          break
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

  function addMessage(role: Message['role'], content: string) {
    messages.value.push({
      id: crypto.randomUUID(),
      role,
      content,
      timestamp: new Date(),
    })
  }

  async function sendUserMessage(text: string) {
    if (!text.trim() || isProcessing.value) return

    addMessage('user', text)
    isProcessing.value = true
    error.value = null

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
      }) as { text: string; metrics?: { token_count: number } }

      addMessage('assistant', response.text)
      
      if (response.metrics?.token_count) {
        tokenCount.value = response.metrics.token_count
      }

      // Refresh credit balance after each message
      if (authStore.isAuthenticated) {
        authStore.refreshCreditBalance()
      }
    } catch (e) {
      error.value = (e as Error).message
      addMessage('system', `Error: ${error.value}`)
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

  function clearMessages() {
    messages.value = []
  }

  return {
    connected,
    godotConnected,
    messages,
    isProcessing,
    tokenCount,
    pendingConfirmation,
    error,
    projectInfo,
    startBrain,
    stopBrain,
    connectWebSocket,
    disconnectWebSocket,
    sendUserMessage,
    respondToConfirmation,
    clearMessages,
  }
})
