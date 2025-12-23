<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useArtifactsStore } from '@/stores/artifacts'
import { safeHighlight } from '@/utils/highlight'

const artifactsStore = useArtifactsStore()

const copied = ref(false)

const highlightedCode = computed(() => {
  if (!artifactsStore.currentArtifact) return ''
  
  return safeHighlight(
    artifactsStore.currentArtifact.content,
    artifactsStore.currentArtifact.language
  )
})

async function copyCode() {
  if (!artifactsStore.currentArtifact) return
  
  const success = await artifactsStore.copyToClipboard(artifactsStore.currentArtifact.content)
  if (success) {
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  }
}

function close() {
  artifactsStore.closeArtifact()
}

// Reset copied state when artifact changes
watch(() => artifactsStore.currentArtifact, () => {
  copied.value = false
})
</script>

<template>
  <!-- Backdrop -->
  <Transition name="fade">
    <div 
      v-if="artifactsStore.isOpen" 
      class="fixed inset-0 bg-black/40 z-40"
      @click="close"
    ></div>
  </Transition>
  
  <!-- Panel -->
  <Transition name="slide">
    <div 
      v-if="artifactsStore.isOpen && artifactsStore.currentArtifact"
      class="fixed top-0 right-0 h-full w-[600px] max-w-[90vw] bg-[#1a1e29] border-l border-[#3b4458] z-50 flex flex-col shadow-2xl"
    >
      <!-- Header -->
      <div class="flex items-center justify-between px-4 py-3 border-b border-[#3b4458] bg-[#202531]">
        <div class="flex items-center gap-3 min-w-0">
          <div class="w-8 h-8 rounded-lg bg-[#478cbf]/20 flex items-center justify-center flex-shrink-0">
            <svg class="w-4 h-4 text-[#478cbf]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
          </div>
          <div class="min-w-0">
            <h3 class="font-semibold text-gray-200 text-sm truncate">{{ artifactsStore.currentArtifact.title }}</h3>
            <span class="text-xs text-gray-500 font-mono">{{ artifactsStore.currentArtifact.lineCount }} lines</span>
          </div>
        </div>
        
        <div class="flex items-center gap-2">
          <!-- Copy Button -->
          <button
            @click="copyCode"
            class="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-[#3b4458] bg-[#2d3546] hover:bg-[#3b4458] transition-colors"
            :class="copied ? 'text-green-400 border-green-500/50' : 'text-gray-400 hover:text-white'"
          >
            <svg v-if="!copied" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <svg v-else class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            {{ copied ? 'Copied!' : 'Copy' }}
          </button>
          
          <!-- Close Button -->
          <button
            @click="close"
            class="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-[#3b4458] transition-colors"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>
      
      <!-- Content -->
      <div class="flex-1 overflow-auto">
        <pre class="p-4 text-sm leading-relaxed"><code class="hljs" :class="`language-${artifactsStore.currentArtifact.language}`" v-html="highlightedCode"></code></pre>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
/* Fade transition for backdrop */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Slide transition for panel */
.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateX(100%);
}
</style>
