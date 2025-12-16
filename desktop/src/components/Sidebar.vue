<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'
import { useBrainStore } from '@/stores/brain'
import iconUrl from '@/assets/icon.svg'

const { isOpen } = defineProps<{
  isOpen?: boolean
}>()

const router = useRouter()
const authStore = useAuthStore()
const sessionsStore = useSessionsStore()
const brainStore = useBrainStore()

// Deletion confirmation state
const sessionToDelete = ref<string | null>(null)

// Use sessions from the store
const sessions = computed(() => sessionsStore.sessions)
const activeSessionId = computed(() => sessionsStore.activeSessionId)

async function createNewSession() {
    await brainStore.clearMessages()
    router.push('/')
}

async function switchSession(sessionId: string) {
    if (sessionId === activeSessionId.value) return
    await brainStore.loadSessionMessages(sessionId)
    router.push('/')
}

function confirmDelete(sessionId: string, event: Event) {
    event.stopPropagation()
    sessionToDelete.value = sessionId
}

async function deleteSession() {
    if (!sessionToDelete.value) return
    const sessionId = sessionToDelete.value
    const wasActive = sessionId === activeSessionId.value
    sessionToDelete.value = null
    
    await sessionsStore.deleteSession(sessionId)
    
    // If we deleted the active session, clear the chat
    if (wasActive) {
        brainStore.messages = []
        brainStore.resetSessionMetrics()
    }
}

function cancelDelete() {
    sessionToDelete.value = null
}

// Format date for display
function formatDate(date: Date): string {
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))
    
    if (days === 0) {
        return 'Today'
    } else if (days === 1) {
        return 'Yesterday'
    } else if (days < 7) {
        return `${days} days ago`
    } else {
        return date.toLocaleDateString()
    }
}
</script>

<template>
  <aside 
    class="flex-shrink-0 bg-[#1a1e29] border-r border-[#2d3546] flex flex-col transition-all duration-300 ease-in-out overflow-hidden"
    :class="[isOpen ? 'w-64' : 'w-0 border-r-0']"
  >
    <!-- Header / Logo -->
    <div class="p-4 flex items-center justify-between border-b border-[#2d3546]">
        <div class="flex items-center space-x-2 font-bold text-[#478cbf]">
            <img :src="iconUrl" alt="Godoty" class="w-6 h-6" />
            <span>GODOTY</span>
        </div>
        <button @click="createNewSession" class="p-1.5 hover:bg-[#2d3546] rounded-md transition-colors text-gray-400 hover:text-white" title="New Chat">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
            </svg>
        </button>
    </div>

    <!-- History / Navigation -->
    <div class="flex-1 overflow-y-auto py-2">
        <div class="px-4 pb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">History</div>
        
        <!-- Loading state -->
        <div v-if="sessionsStore.isLoading" class="px-4 py-3 text-sm text-gray-500">
            Loading sessions...
        </div>
        
        <!-- Empty state -->
        <div v-else-if="sessions.length === 0" class="px-4 py-3 text-sm text-gray-500">
            No sessions yet
        </div>
        
        <!-- Session list -->
        <div 
            v-for="session in sessions" 
            :key="session.id"
            @click="switchSession(session.id)"
            class="group w-full text-left px-4 py-3 text-sm hover:bg-[#2d3546] transition-colors border-l-2 cursor-pointer flex items-center justify-between"
            :class="[
                activeSessionId === session.id 
                ? 'border-[#478cbf] bg-[#262c3b] text-white' 
                : 'border-transparent text-gray-400'
            ]"
        >
            <div class="flex-1 min-w-0 mr-2">
                <div class="truncate">{{ session.title }}</div>
                <div class="text-xs text-gray-500 mt-0.5">{{ formatDate(session.updatedAt) }}</div>
            </div>
            
            <!-- Delete button (show on hover) -->
            <button 
                @click="confirmDelete(session.id, $event)"
                class="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-500/20 rounded transition-all text-gray-500 hover:text-red-400"
                title="Delete session"
            >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                </svg>
            </button>
        </div>
    </div>
    
    <!-- User Profile -->
    <div class="p-4 border-t border-[#2d3546]">
        <div v-if="authStore.user" class="flex items-center justify-between w-full">
            <div class="flex items-center space-x-3 min-w-0 flex-1">
                <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-[#478cbf] to-cyan-400 flex items-center justify-center text-xs font-bold text-white shrink-0">
                    {{ authStore.user.email?.charAt(0).toUpperCase() }}
                </div>
                <div class="text-sm min-w-0 overflow-hidden flex-1">
                    <div class="font-medium text-gray-200 truncate">{{ authStore.user.email }}</div>
                    <div class="text-xs text-[#478cbf] font-mono">
                         {{ authStore.formattedRemainingCredits }} credits
                    </div>
                </div>
            </div>
            <button 
                @click="router.push('/settings')"
                class="ml-2 p-1.5 text-gray-400 hover:text-white hover:bg-[#2d3546] rounded-md transition-colors flex-shrink-0"
                title="Settings"
            >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 0 1 0 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 0 1 0-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281Z" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                </svg>
            </button>
        </div>
        <div v-else class="text-sm text-gray-500">
            Please sign in
        </div>
    </div>
    
    <!-- Delete Confirmation Modal -->
    <Teleport to="body">
      <div v-if="sessionToDelete" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
        <div class="bg-[#2d3546] rounded-xl p-6 max-w-sm w-full mx-4 shadow-2xl border border-[#3b4458]">
          <h3 class="text-lg font-semibold text-white mb-2">Delete Session?</h3>
          <p class="text-gray-300 text-sm mb-6">
            This will permanently delete the session and its entire conversation history.
          </p>
          <div class="flex gap-3 justify-end">
            <button
              @click="cancelDelete"
              class="px-4 py-2 rounded-lg text-gray-300 hover:bg-[#3b4458] transition-all"
            >
              Cancel
            </button>
            <button
              @click="deleteSession"
              class="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white transition-all"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </aside>
</template>
