<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

async function handleSignOut() {
  await authStore.signOut()
  router.push('/login')
}
</script>

<template>
  <div class="flex h-full">
    <!-- Sidebar placeholder for consistency -->
    <div class="w-64 bg-godot-darker border-r border-godot-border p-4">
      <button @click="router.push('/')" class="text-godot-muted hover:text-godot-text mb-4">
        ← Back to Chat
      </button>
    </div>

    <!-- Settings Content -->
    <div class="flex-1 p-8 overflow-y-auto">
      <h1 class="text-2xl font-bold mb-8">Settings</h1>

      <!-- Account Section -->
      <section class="card p-6 mb-6">
        <h2 class="text-lg font-semibold mb-4">Account</h2>
        
        <div v-if="authStore.user" class="space-y-4">
          <div>
            <label class="block text-sm text-godot-muted mb-1">Email</label>
            <p class="text-godot-text">{{ authStore.user.email }}</p>
          </div>
          
          <div>
            <label class="block text-sm text-godot-muted mb-1">User ID</label>
            <p class="text-godot-text font-mono text-sm">{{ authStore.user.id }}</p>
          </div>

          <button @click="handleSignOut" class="btn btn-danger">
            Sign Out
          </button>
        </div>
      </section>

      <!-- Connection Section -->
      <section class="card p-6 mb-6">
        <h2 class="text-lg font-semibold mb-4">Connection</h2>
        
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-godot-muted mb-1">Brain Server URL</label>
            <input
              type="text"
              value="ws://127.0.0.1:8000/ws/tauri"
              disabled
              class="input bg-godot-dark"
            />
            <p class="text-xs text-godot-muted mt-1">The Python brain runs as a sidecar process</p>
          </div>
        </div>
      </section>

      <!-- About Section -->
      <section class="card p-6">
        <h2 class="text-lg font-semibold mb-4">About</h2>
        
        <div class="space-y-2 text-sm text-godot-muted">
          <p>Godoty v0.1.0</p>
          <p>AI-powered assistant for Godot game development</p>
        </div>
      </section>
    </div>
  </div>
</template>
