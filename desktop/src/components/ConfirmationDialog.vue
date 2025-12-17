<script setup lang="ts">
import { ref, computed } from 'vue'
import type { PendingConfirmation } from '@/stores/brain'

const props = defineProps<{
  confirmation: PendingConfirmation
}>()

const emit = defineEmits<{
  respond: [approved: boolean, modifiedContent?: string]
}>()

const editedContent = ref(props.confirmation.details.content || '')
const showDiff = ref(false)

const actionLabel = computed(() => {
  switch (props.confirmation.action_type) {
    case 'write_file': return 'Write File'
    case 'set_setting': return 'Change Setting'
    case 'create_node': return 'Create Node'
    case 'delete_node': return 'Delete Node'
    case 'delete_file': return 'Delete File'
    default: return 'Action'
  }
})

const actionIcon = computed(() => {
  switch (props.confirmation.action_type) {
    case 'write_file': return '📝'
    case 'set_setting': return '⚙️'
    case 'create_node': return '➕'
    case 'delete_node': return '🗑️'
    case 'delete_file': return '🗑️'
    default: return '❓'
  }
})

// Simple diff calculation
const diffLines = computed(() => {
  if (!props.confirmation.details.original_content || !props.confirmation.details.content) {
    return []
  }
  
  const original = props.confirmation.details.original_content.split('\n')
  const modified = props.confirmation.details.content.split('\n')
  const diff: Array<{ type: 'same' | 'add' | 'remove', content: string }> = []
  
  const maxLen = Math.max(original.length, modified.length)
  for (let i = 0; i < maxLen; i++) {
    const origLine = original[i]
    const modLine = modified[i]
    
    if (origLine === modLine) {
      diff.push({ type: 'same', content: origLine || '' })
    } else {
      if (origLine !== undefined) {
        diff.push({ type: 'remove', content: origLine })
      }
      if (modLine !== undefined) {
        diff.push({ type: 'add', content: modLine })
      }
    }
  }
  
  return diff
})

function approve() {
  emit('respond', true, editedContent.value)
}

function deny() {
  emit('respond', false)
}
</script>

<template>
  <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
    <div class="card w-full max-w-4xl max-h-[90vh] flex flex-col">
      <!-- Header -->
      <div class="flex items-center justify-between p-4 border-b border-godot-border">
        <div class="flex items-center gap-3">
          <span class="text-2xl">{{ actionIcon }}</span>
          <div>
            <h2 class="text-lg font-semibold">{{ actionLabel }}</h2>
            <p class="text-sm text-godot-muted">{{ confirmation.description }}</p>
          </div>
        </div>
        <button @click="deny" class="text-godot-muted hover:text-godot-text">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-4">
        <!-- File Path -->
        <div v-if="confirmation.details.path" class="mb-4">
          <label class="block text-sm text-godot-muted mb-1">File Path</label>
          <code class="block bg-godot-darker px-3 py-2 rounded text-godot-blue text-sm">
            {{ confirmation.details.path }}
          </code>
        </div>

        <!-- Setting Path & Value -->
        <div v-if="confirmation.details.setting_path" class="mb-4 space-y-2">
          <div>
            <label class="block text-sm text-godot-muted mb-1">Setting</label>
            <code class="block bg-godot-darker px-3 py-2 rounded text-godot-blue text-sm">
              {{ confirmation.details.setting_path }}
            </code>
          </div>
          <div>
            <label class="block text-sm text-godot-muted mb-1">New Value</label>
            <code class="block bg-godot-darker px-3 py-2 rounded text-sm">
              {{ confirmation.details.value }}
            </code>
          </div>
        </div>

        <!-- Node Info -->
        <div v-if="confirmation.details.node_name" class="mb-4 space-y-2">
          <div>
            <label class="block text-sm text-godot-muted mb-1">Node Name</label>
            <code class="block bg-godot-darker px-3 py-2 rounded text-sm">
              {{ confirmation.details.node_name }}
            </code>
          </div>
          <div v-if="confirmation.details.node_type">
            <label class="block text-sm text-godot-muted mb-1">Node Type</label>
            <code class="block bg-godot-darker px-3 py-2 rounded text-godot-blue text-sm">
              {{ confirmation.details.node_type }}
            </code>
          </div>
        </div>

        <!-- Tab Switcher (for file content) -->
        <div v-if="confirmation.details.content" class="mb-4">
          <div class="flex gap-2 mb-2">
            <button 
              @click="showDiff = false"
              class="px-3 py-1 rounded text-sm"
              :class="!showDiff ? 'bg-godot-blue text-white' : 'bg-godot-darker text-godot-muted'"
            >
              Preview
            </button>
            <button 
              v-if="confirmation.details.original_content"
              @click="showDiff = true"
              class="px-3 py-1 rounded text-sm"
              :class="showDiff ? 'bg-godot-blue text-white' : 'bg-godot-darker text-godot-muted'"
            >
              Diff
            </button>
          </div>

          <!-- Preview / Edit -->
          <div v-if="!showDiff">
            <label class="block text-sm text-godot-muted mb-1">Content (editable)</label>
            <textarea
              v-model="editedContent"
              class="w-full h-80 bg-godot-darker border border-godot-border rounded-lg p-3 font-mono text-sm resize-none focus:outline-none focus:ring-2 focus:ring-godot-blue"
              spellcheck="false"
            />
          </div>

          <!-- Diff View -->
          <div v-else class="bg-godot-darker border border-godot-border rounded-lg p-3 h-80 overflow-y-auto font-mono text-sm">
            <div 
              v-for="(line, i) in diffLines" 
              :key="i"
              class="whitespace-pre"
              :class="{
                'text-green-400 bg-green-900/20': line.type === 'add',
                'text-red-400 bg-red-900/20': line.type === 'remove',
              }"
            >
              <span class="select-none w-6 inline-block text-godot-muted">
                {{ line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' ' }}
              </span>
              {{ line.content }}
            </div>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="flex justify-end gap-3 p-4 border-t border-godot-border">
        <button @click="deny" class="btn btn-secondary">
          Deny
        </button>
        <button @click="approve" class="btn btn-success">
          Approve
        </button>
      </div>
    </div>
  </div>
</template>
