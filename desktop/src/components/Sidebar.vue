<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useBrainStore } from '@/stores/brain'

const router = useRouter()
const authStore = useAuthStore()
const brainStore = useBrainStore()
</script>

<template>
  <aside class="w-64 bg-godot-darker border-r border-godot-border flex flex-col">
    <!-- Logo -->
    <div class="p-4 border-b border-godot-border">
      <div class="flex items-center gap-2">
        <span class="text-2xl">🎮</span>
        <span class="text-xl font-bold text-godot-blue">Godoty</span>
      </div>
    </div>

    <!-- Project Info -->
    <div v-if="brainStore.projectInfo" class="p-4 border-b border-godot-border">
      <div class="text-sm">
        <div class="text-godot-muted mb-1">Connected Project</div>
        <div class="font-medium truncate">{{ brainStore.projectInfo.name }}</div>
        <div class="text-xs text-godot-muted truncate">{{ brainStore.projectInfo.path }}</div>
      </div>
    </div>
    <div v-else class="p-4 border-b border-godot-border">
      <div class="text-sm text-godot-muted">
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></span>
          Waiting for Godot...
        </div>
        <p class="text-xs mt-2">Open a Godot project with the Godoty plugin enabled</p>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 p-2">
      <button
        @click="router.push('/')"
        class="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left hover:bg-godot-surface transition-colors"
        :class="{ 'bg-godot-surface': router.currentRoute.value.path === '/' }"
      >
        <span>💬</span>
        <span>Chat</span>
      </button>
      
      <button
        @click="router.push('/settings')"
        class="w-full flex items-center gap-3 px-3 py-2 rounded-md text-left hover:bg-godot-surface transition-colors"
        :class="{ 'bg-godot-surface': router.currentRoute.value.path === '/settings' }"
      >
        <span>⚙️</span>
        <span>Settings</span>
      </button>
    </nav>

    <!-- User Info -->
    <div class="p-4 border-t border-godot-border">
      <div v-if="authStore.user" class="flex items-center gap-3">
        <div class="w-8 h-8 bg-godot-blue rounded-full flex items-center justify-center text-white text-sm font-medium">
          {{ authStore.user.email?.charAt(0).toUpperCase() }}
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium truncate">{{ authStore.user.email }}</div>
        </div>
      </div>
    </div>
  </aside>
</template>
