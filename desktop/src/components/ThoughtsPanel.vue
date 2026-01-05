<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { ReasoningStep } from '@/stores/brain'

const props = defineProps<{
  thoughts: ReasoningStep[],
  isActive?: boolean
}>()

const thoughtsContainer = ref<HTMLElement | null>(null)
const isExpanded = ref(props.isActive || false)

watch(() => props.isActive, (newVal, oldVal) => {
  if (newVal) {
    // Reasoning started - expand the panel
    isExpanded.value = true
    scrollToBottom()
  } else if (oldVal && !newVal) {
    // Reasoning completed - collapse the panel
    isExpanded.value = false
  }
})

watch(() => props.thoughts.length, () => {
  if (isExpanded.value) {
    scrollToBottom()
  }
})

// Watch for content changes in the last thought (for streaming deltas)
watch(() => props.thoughts[props.thoughts.length - 1]?.content, () => {
  if (isExpanded.value) {
    scrollToBottom()
  }
})

function scrollToBottom() {
  nextTick(() => {
    if (thoughtsContainer.value) {
      thoughtsContainer.value.scrollTop = thoughtsContainer.value.scrollHeight
    }
  })
}

const hasThoughts = computed(() => props.thoughts && props.thoughts.length > 0)

const processedThoughts = computed(() => {
  if (!props.thoughts) return []
  return props.thoughts.map((t, index) => {
    return {
      ...t,
      id: `thought-${index}`,
    }
  })
})

function toggle() {
  isExpanded.value = !isExpanded.value
  if (isExpanded.value) {
    scrollToBottom()
  }
}
</script>

<template>
  <div v-if="hasThoughts" class="thoughts-panel mb-3">
    <button 
      @click="toggle"
      class="flex items-center gap-2 text-xs text-gray-400 hover:text-gray-300 transition-colors py-1 px-2 rounded-lg hover:bg-[#2d3546]/50"
    >
      <svg 
        class="w-3.5 h-3.5 transition-transform duration-200" 
        :class="{ 'rotate-90': isExpanded }"
        fill="none" 
        stroke="currentColor" 
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
      </svg>
      <svg class="w-3.5 h-3.5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
      <span>{{ thoughts.length }} thought{{ thoughts.length !== 1 ? 's' : '' }}</span>
    </button>
    
    <!-- Collapsible content -->
    <div 
      class="overflow-hidden transition-all duration-300 ease-in-out"
      :style="{ maxHeight: isExpanded ? '500px' : '0px' }"
    >
      <div 
        ref="thoughtsContainer"
        class="mt-2 space-y-2 pl-6 border-l-2 border-purple-500/30 overflow-y-auto max-h-[300px] pr-2 custom-scrollbar"
      >
        <div 
          v-for="thought in processedThoughts" 
          :key="thought.id"
          class="text-xs text-gray-400 bg-[#1a1e29]/50 rounded px-3 py-2"
        >
          <span class="italic leading-relaxed whitespace-pre-wrap break-words">{{ thought.content }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.thoughts-panel {
  font-size: 0.75rem;
}
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: rgba(0, 0, 0, 0.1);
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(100, 100, 100, 0.3);
  border-radius: 2px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(100, 100, 100, 0.5);
}
</style>
