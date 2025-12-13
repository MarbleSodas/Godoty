<script setup lang="ts">
import { useBrainStore } from '@/stores/brain'
import ChatPanel from '@/components/ChatPanel.vue'
import ConnectionStatus from '@/components/ConnectionStatus.vue'
import ConfirmationDialog from '@/components/ConfirmationDialog.vue'
import Sidebar from '@/components/Sidebar.vue'

const brainStore = useBrainStore()
</script>

<template>
  <div class="flex h-full">
    <!-- Sidebar -->
    <Sidebar />

    <!-- Main Content -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- Header -->
      <header class="flex items-center justify-between px-4 py-3 border-b border-godot-border bg-godot-surface">
        <div class="flex items-center gap-3">
          <h1 class="text-lg font-semibold">Godoty Assistant</h1>
          <ConnectionStatus />
        </div>
        
        <div class="flex items-center gap-4 text-sm text-godot-muted">
          <span v-if="brainStore.projectInfo">
            {{ brainStore.projectInfo.name }}
          </span>
          <span>Tokens: {{ brainStore.tokenCount.toLocaleString() }}</span>
        </div>
      </header>

      <!-- Chat Area -->
      <ChatPanel class="flex-1" />
    </div>

    <!-- Confirmation Dialog -->
    <ConfirmationDialog 
      v-if="brainStore.pendingConfirmation"
      :confirmation="brainStore.pendingConfirmation"
      @respond="brainStore.respondToConfirmation"
    />
  </div>
</template>
