<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useBrainStore } from '@/stores/brain'
import { useAuthStore } from '@/stores/auth'
import MessageBubble from './MessageBubble.vue'
import type { ModelId } from '@/lib/litellmKeys'

const brainStore = useBrainStore()
const authStore = useAuthStore()
const input = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const showModelSelector = ref(false)

// Get display name for a model
function getModelDisplayName(modelId: string): string {
  const model = authStore.availableModels.find((m: { id: string }) => m.id === modelId)
  return model?.name ?? modelId
}

function selectModel(modelId: ModelId) {
  authStore.setSelectedModelId(modelId)
  showModelSelector.value = false
}

async function sendMessage() {
  if (!input.value.trim() || brainStore.isProcessing) return
  
  const text = input.value
  input.value = ''
  
  await brainStore.sendUserMessage(text)
}

// Auto-scroll to bottom when new messages arrive
watch(() => brainStore.messages.length, async () => {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
})

// Close model selector when clicking outside
function handleClickOutside(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (!target.closest('.model-selector')) {
    showModelSelector.value = false
  }
}
</script>

<template>
  <div class="flex flex-col h-full" @click="handleClickOutside">
    <!-- Messages -->
    <div 
      ref="messagesContainer"
      class="flex-1 overflow-y-auto p-4 space-y-4"
    >
      <!-- Empty State -->
      <div v-if="brainStore.messages.length === 0" class="h-full flex items-center justify-center">
        <div class="text-center text-godot-muted">
          <div class="text-4xl mb-4">🤖</div>
          <h2 class="text-xl font-semibold mb-2">Welcome to Godoty</h2>
          <p class="max-w-md">
            Ask me to help with your Godot project. I can view your scene tree, 
            read and write scripts, take screenshots, and more.
          </p>
        </div>
      </div>

      <!-- Message List -->
      <MessageBubble
        v-for="message in brainStore.messages"
        :key="message.id"
        :message="message"
      />

      <!-- Processing Indicator -->
      <div v-if="brainStore.isProcessing" class="flex items-center gap-2 text-godot-muted">
        <div class="flex gap-1">
          <span class="w-2 h-2 bg-godot-blue rounded-full animate-bounce" style="animation-delay: 0ms"></span>
          <span class="w-2 h-2 bg-godot-blue rounded-full animate-bounce" style="animation-delay: 150ms"></span>
          <span class="w-2 h-2 bg-godot-blue rounded-full animate-bounce" style="animation-delay: 300ms"></span>
        </div>
        <span class="text-sm">Thinking...</span>
      </div>
    </div>

    <!-- Input Area -->
    <div class="border-t border-godot-border p-4 bg-godot-surface">
      <!-- Model Selector Row -->
      <div class="flex items-center justify-between mb-3">
        <div class="model-selector relative">
          <button
            @click.stop="showModelSelector = !showModelSelector"
            class="flex items-center gap-2 px-3 py-1.5 text-sm rounded-lg bg-godot-bg hover:bg-godot-hover border border-godot-border transition-colors"
          >
            <span class="text-godot-muted">Model:</span>
            <span class="font-medium text-godot-text">{{ getModelDisplayName(authStore.selectedModel) }}</span>
            <svg 
              class="w-4 h-4 text-godot-muted transition-transform"
              :class="{ 'rotate-180': showModelSelector }"
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          
          <!-- Dropdown -->
          <div 
            v-if="showModelSelector"
            class="absolute bottom-full left-0 mb-2 w-64 bg-godot-surface border border-godot-border rounded-lg shadow-lg overflow-hidden z-50"
          >
            <div class="p-2 text-xs text-godot-muted border-b border-godot-border">
              Select Model
            </div>
            <div class="max-h-60 overflow-y-auto">
              <!-- Loading State -->
              <div v-if="authStore.modelsLoading" class="px-3 py-4 text-center text-godot-muted">
                <div class="flex items-center justify-center gap-2">
                  <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span class="text-sm">Loading models...</span>
                </div>
              </div>
              <!-- Models List -->
              <template v-else-if="authStore.availableModels.length > 0">
                <button
                  v-for="model in authStore.availableModels"
                  :key="model.id"
                  @click.stop="selectModel(model.id)"
                  class="w-full px-3 py-2 text-left hover:bg-godot-hover flex items-center justify-between group"
                  :class="{ 'bg-godot-blue/10': authStore.selectedModel === model.id }"
                >
                  <div>
                    <div class="font-medium text-godot-text">{{ model.name }}</div>
                    <div class="text-xs text-godot-muted">{{ model.provider }}</div>
                  </div>
                  <svg 
                    v-if="authStore.selectedModel === model.id"
                    class="w-4 h-4 text-godot-blue"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                  </svg>
                </button>
              </template>
              <!-- Empty State -->
              <div v-else class="px-3 py-4 text-center text-godot-muted">
                <div class="text-sm">No models available</div>
                <div class="text-xs mt-1">Please check your configuration</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Credit Balance Display -->
        <div v-if="authStore.isAuthenticated" class="flex items-center gap-2 text-sm">
          <span class="text-godot-muted">Credits:</span>
          <span 
            class="font-mono font-medium"
            :class="{
              'text-green-400': authStore.remainingCredits > 2,
              'text-yellow-400': authStore.remainingCredits > 0.5 && authStore.remainingCredits <= 2,
              'text-red-400': authStore.remainingCredits <= 0.5
            }"
          >
            ${{ authStore.remainingCredits.toFixed(2) }}
          </span>
          <span class="text-godot-muted">/ ${{ authStore.maxCredits.toFixed(2) }}</span>
          <button 
            @click="authStore.refreshCreditBalance()"
            class="p-1 rounded hover:bg-godot-hover text-godot-muted hover:text-godot-text transition-colors"
            title="Refresh balance"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
      </div>

      <form @submit.prevent="sendMessage" class="flex gap-3">
        <input
          v-model="input"
          type="text"
          placeholder="Ask Godoty anything..."
          :disabled="brainStore.isProcessing"
          class="input flex-1"
          @keydown.enter.prevent="sendMessage"
        />
        <button
          type="submit"
          :disabled="brainStore.isProcessing || !input.trim()"
          class="btn btn-primary px-6"
        >
          Send
        </button>
      </form>
      
      <!-- Error Display -->
      <div v-if="brainStore.error" class="mt-2 text-sm text-red-400">
        {{ brainStore.error }}
      </div>
    </div>
  </div>
</template>
