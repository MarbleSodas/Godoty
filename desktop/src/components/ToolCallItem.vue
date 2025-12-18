<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ToolCall } from '@/stores/brain'

const props = defineProps<{
  call: ToolCall
}>()

const isExpanded = ref(false)

const statusColor = computed(() => {
  switch (props.call.status) {
    case 'running': return 'text-blue-400'
    case 'completed': return 'text-green-400'
    case 'error': return 'text-red-400'
    default: return 'text-gray-400'
  }
})

const statusIcon = computed(() => {
  switch (props.call.status) {
    case 'running': return 'spinner'
    case 'completed': return 'check'
    case 'error': return 'error'
    default: return 'pending'
  }
})

const formattedArgs = computed(() => {
  try {
    return JSON.stringify(props.call.arguments, null, 2)
  } catch {
    return String(props.call.arguments)
  }
})

function toggle() {
  isExpanded.value = !isExpanded.value
}
</script>

<template>
  <div class="tool-call-item mb-2 rounded-lg border border-[#3b4458]/50 bg-[#1a1e29]/50 overflow-hidden">
    <!-- Header -->
    <button 
      @click="toggle"
      class="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-[#2d3546]/30 transition-colors"
    >
      <!-- Status Icon -->
      <div :class="statusColor">
        <!-- Spinner for running -->
        <svg v-if="statusIcon === 'spinner'" class="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
        <!-- Check for completed -->
        <svg v-else-if="statusIcon === 'check'" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
        </svg>
        <!-- Error icon -->
        <svg v-else-if="statusIcon === 'error'" class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
        </svg>
      </div>
      
      <!-- Tool name -->
      <span class="font-mono text-gray-300">{{ call.name }}</span>
      
      <!-- Expand indicator -->
      <svg 
        class="w-3 h-3 ml-auto text-gray-500 transition-transform duration-200" 
        :class="{ 'rotate-90': isExpanded }"
        fill="none" 
        stroke="currentColor" 
        viewBox="0 0 24 24"
      >
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
      </svg>
    </button>
    
    <!-- Collapsible Details -->
    <div 
      class="overflow-hidden transition-all duration-300 ease-in-out"
      :style="{ maxHeight: isExpanded ? '400px' : '0px' }"
    >
      <div class="px-3 pb-3 space-y-2 text-xs">
        <!-- Arguments -->
        <div v-if="call.arguments && Object.keys(call.arguments).length > 0">
          <div class="text-gray-500 mb-1">Arguments:</div>
          <pre class="bg-[#0d1117] rounded p-2 text-gray-400 overflow-x-auto text-[10px]">{{ formattedArgs }}</pre>
        </div>
        
        <!-- Result -->
        <div v-if="call.result">
          <div class="text-gray-500 mb-1">Result:</div>
          <pre class="bg-[#0d1117] rounded p-2 text-gray-400 overflow-x-auto text-[10px] max-h-40 overflow-y-auto">{{ call.result }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-call-item pre {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
