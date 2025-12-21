<script setup lang="ts">
import { ref, nextTick, watch, onMounted, onUnmounted, computed } from 'vue'
import { useBrainStore } from '@/stores/brain'
import { useAuthStore } from '@/stores/auth'
import MessageBubble from './MessageBubble.vue'
import type { ModelId } from '@/lib/litellmKeys'

import iconUrl from '@/assets/icon.svg'

const brainStore = useBrainStore()
const authStore = useAuthStore()
const input = ref('')
const showModelSelector = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const textarea = ref<HTMLTextAreaElement | null>(null)

async function sendMessage() {
  if (!input.value.trim() || brainStore.isProcessing) return
  
  const text = input.value
  input.value = ''
  autoResize() // Reset height
  
  await brainStore.sendUserMessage(text)
}

// Get display name for a model
function getModelDisplayName(modelId: string): string {
  const model = authStore.availableModels.find((m: { id: string }) => m.id === modelId)
  return model?.name ?? modelId
}

function selectModel(modelId: ModelId) {
  authStore.setSelectedModelId(modelId)
  showModelSelector.value = false
}

function openPricing() {
  authStore.openPricingPage()
  brainStore.dismissPurchasePrompt()
}

function autoResize() {
  if (textarea.value) {
    textarea.value.style.height = 'auto'
    textarea.value.style.height = textarea.value.scrollHeight + 'px'
  }
}



// Track if user is near the bottom of the scroll area
const userIsNearBottom = ref(true)
const SCROLL_THRESHOLD = 150 // pixels from bottom to consider "near bottom"

function checkIfNearBottom() {
  if (messagesContainer.value) {
    const { scrollTop, scrollHeight, clientHeight } = messagesContainer.value
    userIsNearBottom.value = scrollHeight - scrollTop - clientHeight < SCROLL_THRESHOLD
  }
}

function scrollToBottom() {
  if (messagesContainer.value && userIsNearBottom.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

// Computed to get the currently streaming message content (for watching)
const streamingContent = computed(() => {
  const streamingMsg = brainStore.messages.find(m => m.isStreaming)
  return streamingMsg?.content || ''
})

// Auto-scroll when new messages arrive
watch(() => brainStore.messages.length, async () => {
  await nextTick()
  // Always scroll to bottom on new message
  if (messagesContainer.value) {
    userIsNearBottom.value = true
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
})

// Auto-scroll during streaming if user is near bottom
watch(streamingContent, async () => {
  await nextTick()
  scrollToBottom()
})

// Focus input on mount
const handleOutsideClick = (e: Event) => {
    const target = e.target as HTMLElement
    if (!target.closest('.model-selector')) {
        showModelSelector.value = false
    }
}

onMounted(() => {
    textarea.value?.focus()
    // Click outside to close model selector
    document.addEventListener('click', handleOutsideClick)
    
    // Check URL params and refresh balance periodically when app regains focus
    // This catches purchases made on the website
    window.addEventListener('focus', () => {
      if (authStore.isAuthenticated) {
        authStore.refreshCreditBalance()
      }
    })
})

onUnmounted(() => {
    document.removeEventListener('click', handleOutsideClick)
})
</script>

<template>
  <div class="flex flex-col h-full bg-[#202531]">



    <!-- Messages -->
    <div 
      ref="messagesContainer"
      class="flex-1 overflow-y-auto p-4 scroll-smooth"
      @scroll="checkIfNearBottom"
    >
      <div class="max-w-3xl mx-auto space-y-6 pb-20">
          <!-- Empty State -->
          <div v-if="!brainStore.isProcessing && brainStore.messages.length === 0" class="flex flex-col items-center justify-center h-full py-20 opacity-50 select-none">
            <div class="w-16 h-16 bg-[#2d3546] rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-[#478cbf]/10">
                <img :src="iconUrl" class="w-10 h-10 opacity-70" alt="Godoty" />
            </div>
            <h2 class="text-xl font-medium text-gray-300">How can I help with your Godot project?</h2>
            <p class="text-sm text-gray-500 mt-2">Ask about GDScript, shaders, or scene composition.</p>
          </div>

          <!-- Loading State -->
          <div v-else-if="brainStore.isProcessing && brainStore.messages.length === 0" class="flex flex-col items-center justify-center h-full py-20 opacity-50 select-none animate-pulse">
            <div class="w-16 h-16 bg-[#2d3546] rounded-2xl mb-4"></div>
            <div class="h-6 w-64 bg-[#2d3546] rounded mb-3"></div>
            <div class="h-4 w-48 bg-[#2d3546] rounded"></div>
            <p class="text-sm text-gray-500 mt-8">Loading session...</p>
          </div>

          <!-- Message List -->
          <MessageBubble
            v-for="message in brainStore.messages"
            :key="message.id"
            :message="message"
          />

          <!-- Processing Indicator (at bottom of chat) - only show when NOT streaming -->
          <div v-if="brainStore.isProcessing && !brainStore.messages.some(m => m.isStreaming)" class="flex items-center gap-2 text-godot-muted animate-fade-in pl-4">
             <div class="flex gap-1">
                <span class="w-1.5 h-1.5 bg-[#478cbf] rounded-full animate-bounce" style="animation-delay: 0ms"></span>
                <span class="w-1.5 h-1.5 bg-[#478cbf] rounded-full animate-bounce" style="animation-delay: 150ms"></span>
                <span class="w-1.5 h-1.5 bg-[#478cbf] rounded-full animate-bounce" style="animation-delay: 300ms"></span>
             </div>
          </div>
      </div>
    </div>

    <!-- Input Area -->
    <div class="p-4 bg-[#202531]">
        <div class="max-w-3xl mx-auto bg-[#2d3546] rounded-xl shadow-lg border border-[#3b4458] focus-within:border-[#478cbf] focus-within:ring-1 focus-within:ring-[#478cbf]/50 transition-all duration-200">
            <textarea
                ref="textarea"
                v-model="input"
                @keydown.enter.prevent="sendMessage"
                @input="autoResize"
                placeholder="Ask Godoty a question..."
                class="w-full bg-transparent text-gray-200 placeholder-gray-500 text-sm px-4 py-3 rounded-xl focus:outline-none resize-none overflow-y-auto"
                rows="1"
                style="min-height: 48px; max-height: 200px;"
            ></textarea>

            <div class="flex items-center justify-between px-3 pb-3 pt-1 border-t border-[#3b4458]/50">
                <!-- Model Selector (Left) -->
                 <div class="model-selector relative">
                    <button
                        @click.stop="showModelSelector = !showModelSelector"
                        class="flex items-center gap-2 px-2 py-1.5 text-xs rounded-lg border border-[#3b4458] bg-[#1a1e29] text-gray-400 hover:text-gray-200 hover:bg-[#3b4458] transition-all"
                        :title="getModelDisplayName(authStore.selectedModel)"
                    >
                        <span class="font-medium truncate max-w-[200px]">{{ getModelDisplayName(authStore.selectedModel) }}</span>
                        <svg class="w-3 h-3 text-gray-500" :class="{ 'rotate-180': showModelSelector }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                        </svg>
                    </button>

                     <!-- Dropdown -->
                    <div v-if="showModelSelector" class="absolute left-0 bottom-full mb-2 w-64 bg-[#2d3546] border border-[#3b4458] rounded-lg shadow-xl overflow-hidden z-20">
                         <div class="max-h-60 overflow-y-auto py-1">
                            <button
                                v-for="model in authStore.availableModels"
                                :key="model.id"
                                @click="selectModel(model.id)"
                                class="w-full px-3 py-2 text-left text-xs hover:bg-[#3b4458] flex items-center justify-between group"
                                :class="authStore.selectedModel === model.id ? 'text-[#478cbf]' : 'text-gray-300'"
                            >
                                <span class="truncate">{{ model.name }}</span>
                                <svg v-if="authStore.selectedModel === model.id" class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                                </svg>
                            </button>
                         </div>
                    </div>
                 </div>

                <!-- Right Actions -->
                <div class="flex items-center gap-2">
                    <button
                        v-if="brainStore.processingSessionId !== null"
                        @click="brainStore.cancelCurrentRequest()"
                        class="p-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-all"
                        title="Cancel generation"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
                            <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                        </svg>
                    </button>

                    <button 
                        @click="sendMessage"
                        :disabled="!input.trim() || brainStore.processingSessionId !== null"
                        class="p-1.5 rounded-lg bg-[#478cbf] text-white hover:bg-[#367fa9] disabled:opacity-50 disabled:bg-transparent disabled:text-gray-500 transition-all"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
                            <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A2 2 0 005.635 9.75h5.736a.75.75 0 010 1.5H5.636a2 2 0 00-1.942 1.586l-1.414 4.925a.75.75 0 00.826.95 28.89 28.89 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
                        </svg>
                    </button>
                </div>
            </div>
        </div>
        <div class="text-center text-[10px] text-gray-600 mt-2 font-mono">
           Godoty can make mistakes. Check generated code in the Godot docs.
        </div>
        
        <!-- Error Display -->
        <div v-if="brainStore.error" class="mt-2 text-center text-xs text-red-400">
            {{ brainStore.error }}
        </div>
    </div>

    <!-- Purchase Credits Modal -->
    <div v-if="brainStore.showPurchasePrompt" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div class="bg-[#2d3546] rounded-xl p-6 max-w-sm w-full mx-4 shadow-2xl border border-[#3b4458]">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-white">Out of Credits</h3>
          <button @click="brainStore.dismissPurchasePrompt()" class="text-gray-400 hover:text-white">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        
        <p class="text-gray-300 text-sm mb-6">
          You've run out of credits. Purchase more on our website to continue using Godoty.
        </p>
        
        <button
          @click="openPricing"
          class="w-full py-3 px-4 rounded-lg bg-[#478cbf] hover:bg-[#367fa9] text-white font-medium transition-all flex items-center justify-center gap-2"
        >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
          </svg>
          View Pricing
        </button>
        
        <p class="text-xs text-gray-500 mt-4 text-center">
          After purchasing, return here and your balance will update automatically.
        </p>
      </div>
    </div>

    <!-- Toast Notification -->
    <div 
      v-if="brainStore.toast" 
      class="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 animate-fade-in"
    >
      <div 
        :class="[
          'px-4 py-3 rounded-lg shadow-lg flex items-center gap-2 text-sm',
          brainStore.toast.type === 'success' ? 'bg-green-600 text-white' : '',
          brainStore.toast.type === 'error' ? 'bg-red-600 text-white' : '',
          brainStore.toast.type === 'info' ? 'bg-[#478cbf] text-white' : '',
        ]"
      >
        <svg v-if="brainStore.toast.type === 'success'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
        </svg>
        <svg v-if="brainStore.toast.type === 'error'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
        <svg v-if="brainStore.toast.type === 'info'" class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        {{ brainStore.toast.message }}
        <button @click="brainStore.hideToast()" class="ml-2 hover:opacity-80">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
