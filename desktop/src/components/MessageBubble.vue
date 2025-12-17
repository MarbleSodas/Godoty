<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '@/stores/brain'
import { useArtifactsStore } from '@/stores/artifacts'
import { parseMarkdown } from '@/utils/markdown'

const props = defineProps<{
  message: Message
}>()

import iconUrl from '@/assets/icon.svg'

const artifactsStore = useArtifactsStore()

const isUser = computed(() => props.message.role === 'user')
const isSystem = computed(() => props.message.role === 'system')
const isStreaming = computed(() => props.message.isStreaming)

// Use the robust markdown parser
const formattedContent = computed(() => {
  return parseMarkdown(props.message.content)
})

// Format token count for display
function formatTokens(tokens: number): string {
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}k`
  }
  return tokens.toString()
}

// Handle clicks on code block buttons via event delegation
function handleContentClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  const button = target.closest('button')
  if (!button) return
  
  const wrapper = button.closest('.code-block-wrapper') as HTMLElement
  if (!wrapper) return
  
  // Handle copy button
  if (button.classList.contains('code-copy-btn')) {
    const code = decodeURIComponent(wrapper.dataset.code || '')
    copyToClipboard(code, button)
    return
  }
  
  // Handle collapse button
  if (button.classList.contains('code-collapse-btn')) {
    toggleCollapse(wrapper, button)
    return
  }
  
  // Handle view in panel button
  if (button.classList.contains('code-view-panel-btn')) {
    openInPanel(wrapper)
    return
  }
}

async function copyToClipboard(code: string, button: HTMLElement) {
  try {
    await navigator.clipboard.writeText(code)
    const textSpan = button.querySelector('.copy-text')
    if (textSpan) {
      const originalText = textSpan.textContent
      textSpan.textContent = 'Copied!'
      button.classList.add('text-green-400')
      setTimeout(() => {
        textSpan.textContent = originalText
        button.classList.remove('text-green-400')
      }, 2000)
    }
  } catch (e) {
    console.error('Failed to copy:', e)
  }
}

function toggleCollapse(wrapper: HTMLElement, button: HTMLElement) {
  const content = wrapper.querySelector('.code-block-content') as HTMLElement
  const icon = button.querySelector('.collapse-icon') as HTMLElement
  const isCollapsed = button.dataset.collapsed === 'true'
  
  if (isCollapsed) {
    // Expand
    content.style.maxHeight = '600px'
    button.dataset.collapsed = 'false'
    icon.style.transform = 'rotate(0deg)'
  } else {
    // Collapse
    content.style.maxHeight = '0px'
    button.dataset.collapsed = 'true'
    icon.style.transform = 'rotate(-90deg)'
  }
}

function openInPanel(wrapper: HTMLElement) {
  const code = decodeURIComponent(wrapper.dataset.code || '')
  const lang = wrapper.dataset.lang || 'text'
  const artifactId = wrapper.dataset.artifactId || ''
  const lineCount = code.split('\n').length
  
  // Register and open the artifact
  artifactsStore.registerArtifact({
    id: artifactId,
    title: `${lang.charAt(0).toUpperCase() + lang.slice(1)} Code`,
    content: code,
    language: lang,
    lineCount
  })
  artifactsStore.openArtifact(artifactId)
}
</script>

<template>
    <div>
        <!-- User Message -->
        <div v-if="isUser" class="flex justify-end animate-fade-in-up mb-6">
            <div class="bg-[#2d3546] text-gray-100 px-4 py-3 rounded-2xl rounded-tr-sm max-w-[85%] shadow-sm border border-[#3b4458]">
                <div class="text-sm whitespace-pre-wrap leading-relaxed" v-html="formattedContent"></div>
                <div class="text-[10px] text-gray-500 mt-1 text-right">{{ message.timestamp.toLocaleTimeString() }}</div>
            </div>
        </div>

        <!-- System Message -->
        <div v-else-if="isSystem" class="flex justify-center mb-4">
            <div class="bg-[#1a1e29] text-yellow-400 px-4 py-2 rounded-lg text-sm border border-yellow-500/20">
                {{ message.content }}
            </div>
        </div>

        <!-- Assistant Message - only show if streaming OR has content -->
        <div v-else-if="isStreaming || props.message.content" class="flex gap-4 pr-4 mb-6" :class="isStreaming ? 'animate-pulse-subtle' : 'animate-fade-in-up'">
            <div class="flex-shrink-0 mt-1">
                <div class="w-8 h-8 rounded-lg bg-[#478cbf] flex items-center justify-center shadow-lg shadow-blue-500/20">
                    <img :src="iconUrl" class="w-5 h-5 text-white" style="filter: brightness(0) invert(1);" alt="Godoty" />
                </div>
            </div>
            
            <div class="flex-1 space-y-2 min-w-0">
                <!-- Content with fade-up animation for streaming -->
                <!-- Thinking indicator - only show while streaming with no content -->
                <div v-if="isStreaming && !props.message.content" class="flex items-center gap-2 text-gray-500 italic">
                    <span class="w-1.5 h-1.5 bg-[#478cbf] rounded-full animate-ping"></span>
                    Thinking...
                </div>
                
                <!-- Message content -->
                <div 
                    v-else-if="formattedContent"
                    class="prose prose-invert prose-sm max-w-none text-gray-300 leading-relaxed"
                    :class="{ 'streaming-text': isStreaming }"
                    v-html="formattedContent"
                    @click="handleContentClick"
                ></div>
                
                <!-- Message Footer: Timestamp and Metrics -->
                <div class="flex items-center gap-3 text-[10px] text-gray-600">
                    <span>{{ message.timestamp.toLocaleTimeString() }}</span>
                    
                    <!-- Per-message metrics (only for completed assistant messages) -->
                    <template v-if="message.metrics && !isStreaming">
                        <span class="text-gray-700">•</span>
                        <span class="font-mono text-gray-500">
                            {{ formatTokens(message.metrics.inputTokens) }} → {{ formatTokens(message.metrics.outputTokens) }} tokens
                        </span>
                        <span v-if="message.metrics.cost" class="text-green-500/70 font-mono">
                            ${{ message.metrics.cost.toFixed(4) }}
                        </span>
                    </template>
                    
                    <!-- Streaming indicator -->
                    <span v-if="isStreaming && props.message.content" class="text-[#478cbf] flex items-center gap-1">
                        <span class="w-1 h-1 bg-[#478cbf] rounded-full animate-ping"></span>
                        streaming...
                    </span>
                </div>
            </div>
            
        </div>
    </div>
</template>

<style>
/* Highlight.js theme overrides for Godot-like styling */
.hljs {
  color: #e0e0e0;
  background: transparent;
}
.hljs-keyword {
  color: #ff7085;
}
.hljs-string {
  color: #ffeda1;
}
.hljs-number {
  color: #a1ffe0;
}
.hljs-function {
  color: #66d9ef;
}
.hljs-comment {
  color: #6b6b7b;
}
.hljs-built_in {
  color: #a1c4ff;
}

/* Streaming text animation - subtle fade-up effect */
.streaming-text {
  animation: streamFadeIn 0.3s ease-out;
}

@keyframes streamFadeIn {
  from {
    opacity: 0.7;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Subtle pulse for streaming messages */
.animate-pulse-subtle {
  animation: pulseSlight 2s ease-in-out infinite;
}

@keyframes pulseSlight {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.85;
  }
}
</style>
