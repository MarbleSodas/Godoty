<script setup lang="ts">
import { ref, computed } from 'vue'
import { useBrainStore } from '@/stores/brain'
import ChatPanel from '@/components/ChatPanel.vue'
import ConfirmationDialog from '@/components/ConfirmationDialog.vue'
import Sidebar from '@/components/Sidebar.vue'
import ArtifactPanel from '@/components/ArtifactPanel.vue'

const brainStore = useBrainStore()

const sidebarOpen = ref(true)

const projectTitle = computed(() => {
    if (brainStore.projectInfo?.name) {
        return brainStore.projectInfo.name
    }
    return 'Godoty'
})

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

// Debug logs for title issues
import { watch } from 'vue'
watch(() => brainStore.projectInfo, (info) => {
    console.log('[MainView] projectInfo updated:', info)
}, { deep: true })



</script>

<template>
  <div class="flex h-screen w-full">
    <!-- Sidebar -->
    <Sidebar :is-open="sidebarOpen" />

    <!-- Main Content -->
    <main class="flex-1 flex flex-col relative min-w-0 bg-[#202531]">
        
        <!-- Header -->
        <header class="h-14 border-b border-[#2d3546] bg-[#202531]/95 backdrop-blur flex items-center justify-between px-4 z-10 sticky top-0">
            <div class="flex items-center">
                <button @click="toggleSidebar" class="mr-3 p-2 hover:bg-[#2d3546] rounded-md text-gray-400 hover:text-white transition-colors">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                    </svg>
                </button>
                <div class="flex flex-col">
                    <span class="font-semibold text-gray-200 text-sm">
                        {{ projectTitle }}
                    </span>
                    <span class="text-[10px] text-[#478cbf] flex items-center gap-1">
                        <span class="w-1.5 h-1.5 rounded-full animate-pulse" :class="brainStore.connected ? 'bg-green-500' : 'bg-red-500'"></span>
                        {{ brainStore.connected ? 'Online' : 'Offline' }}
                    </span>
                </div>
            </div>

            <!-- Session Metrics -->
            <div v-if="brainStore.messages.length > 0" class="flex items-center gap-4 text-xs font-mono border-l border-[#2d3546] pl-4 ml-4">
              <div class="flex items-center gap-4 text-gray-400">
                <span class="flex items-center gap-1.5">
                  <svg class="w-3.5 h-3.5 text-[#478cbf]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
                  </svg>
                  {{ brainStore.sessionMetrics.messageCount }} msgs
                </span>
                <span class="flex items-center gap-1.5">
                  <svg class="w-3.5 h-3.5 text-[#478cbf]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  {{ brainStore.sessionMetrics.totalTokens.toLocaleString() }} tokens
                </span>
                <span class="flex items-center gap-1.5">
                  <svg class="w-3.5 h-3.5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  ${{ brainStore.sessionMetrics.totalCost.toFixed(4) }}
                </span>
              </div>

            </div>
        </header>

        <!-- Chat Area -->
        <ChatPanel class="flex-1 overflow-hidden" />
        
        <!-- Confirmation Dialog -->
        <ConfirmationDialog 
          v-if="brainStore.pendingConfirmation"
          :confirmation="brainStore.pendingConfirmation"
          @respond="brainStore.respondToConfirmation"
        />

    </main>
    
    <!-- Artifact Panel (slides in from right) -->
    <ArtifactPanel />
  </div>
</template>
