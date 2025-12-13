<script setup lang="ts">
import { useBrainStore } from '@/stores/brain'

const brainStore = useBrainStore()
</script>

<template>
  <div class="flex items-center gap-2">
    <!-- Brain Status -->
    <div class="flex items-center gap-1.5">
      <span 
        class="w-2.5 h-2.5 rounded-full"
        :class="brainStore.connected ? 'bg-green-500' : 'bg-red-500'"
      />
      <span class="text-xs text-godot-muted">
        Brain {{ brainStore.connected ? 'Connected' : 'Disconnected' }}
      </span>
    </div>

    <span class="text-godot-border">|</span>

    <!-- Godot Status -->
    <div class="flex items-center gap-1.5">
      <span 
        class="w-2.5 h-2.5 rounded-full"
        :class="brainStore.godotConnected ? 'bg-blue-500' : 'bg-yellow-500'"
      />
      <span class="text-xs text-godot-muted">
        Godot {{ brainStore.godotConnected ? 'Connected' : 'Waiting...' }}
      </span>
    </div>
  </div>
</template>
