<script setup lang="ts">
import { computed } from 'vue'
import type { Message } from '@/stores/brain'
import hljs from 'highlight.js/lib/core'
import gdscript from 'highlight.js/lib/languages/python' // Using Python as closest match for GDScript

// Register GDScript syntax (using Python as base)
hljs.registerLanguage('gdscript', gdscript)

const props = defineProps<{
  message: Message
}>()

const isUser = computed(() => props.message.role === 'user')
const isSystem = computed(() => props.message.role === 'system')

// Simple markdown-like formatting for code blocks
const formattedContent = computed(() => {
  let content = props.message.content
  
  // Replace code blocks with highlighted versions
  content = content.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) => {
    const language = lang || 'gdscript'
    try {
      const highlighted = hljs.highlight(code.trim(), { language }).value
      return `<pre class="bg-godot-darker rounded-lg p-3 my-2 overflow-x-auto"><code class="hljs language-${language}">${highlighted}</code></pre>`
    } catch {
      return `<pre class="bg-godot-darker rounded-lg p-3 my-2 overflow-x-auto"><code>${code.trim()}</code></pre>`
    }
  })
  
  // Replace inline code
  content = content.replace(/`([^`]+)`/g, '<code class="bg-godot-darker px-1.5 py-0.5 rounded text-godot-blue">$1</code>')
  
  // Replace newlines with <br>
  content = content.replace(/\n/g, '<br>')
  
  return content
})
</script>

<template>
  <div 
    class="flex"
    :class="isUser ? 'justify-end' : 'justify-start'"
  >
    <div 
      class="max-w-[80%] rounded-lg px-4 py-3"
      :class="{
        'bg-godot-blue text-white': isUser,
        'bg-godot-surface border border-godot-border': !isUser && !isSystem,
        'bg-red-900/30 border border-red-700/50 text-red-200': isSystem,
      }"
    >
      <!-- Role Label -->
      <div v-if="!isUser" class="text-xs text-godot-muted mb-1 uppercase tracking-wide">
        {{ message.role }}
      </div>
      
      <!-- Content -->
      <div 
        class="prose prose-invert max-w-none text-sm leading-relaxed"
        v-html="formattedContent"
      />
      
      <!-- Timestamp -->
      <div 
        class="text-xs mt-2 opacity-60"
        :class="isUser ? 'text-right' : 'text-left'"
      >
        {{ message.timestamp.toLocaleTimeString() }}
      </div>
    </div>
  </div>
</template>

<style>
/* Highlight.js theme overrides for Godot-like styling */
.hljs {
  color: #e0e0e0;
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
</style>
