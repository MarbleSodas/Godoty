<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const router = useRouter()

const email = ref('')
const password = ref('')
const isSignUp = ref(false)
const localError = ref<string | null>(null)

async function handleSubmit() {
  localError.value = null
  try {
    if (isSignUp.value) {
      await authStore.signUpWithEmail(email.value, password.value)
    } else {
      await authStore.signInWithEmail(email.value, password.value)
    }
    router.push('/')
  } catch (e) {
    localError.value = (e as Error).message
  }
}

async function handleOAuth(provider: 'github' | 'google') {
  try {
    await authStore.signInWithOAuth(provider)
  } catch (e) {
    localError.value = (e as Error).message
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-godot-dark p-4">
    <div class="card p-8 w-full max-w-md">
      <!-- Logo -->
      <div class="text-center mb-8">
        <h1 class="text-3xl font-bold text-godot-blue">Godoty</h1>
        <p class="text-godot-muted mt-2">AI Assistant for Godot</p>
      </div>

      <!-- Error Message -->
      <div v-if="localError || authStore.error" class="mb-4 p-3 bg-red-900/50 border border-red-700 rounded-md text-red-200 text-sm">
        {{ localError || authStore.error }}
      </div>

      <!-- Auth Form -->
      <form @submit.prevent="handleSubmit" class="space-y-4">
        <div>
          <label for="email" class="block text-sm font-medium text-godot-text mb-1">Email</label>
          <input
            id="email"
            v-model="email"
            type="email"
            required
            class="input"
            placeholder="you@example.com"
          />
        </div>

        <div>
          <label for="password" class="block text-sm font-medium text-godot-text mb-1">Password</label>
          <input
            id="password"
            v-model="password"
            type="password"
            required
            class="input"
            placeholder="••••••••"
            minlength="6"
          />
        </div>

        <button
          type="submit"
          :disabled="authStore.loading"
          class="btn btn-primary w-full"
        >
          <span v-if="authStore.loading">Loading...</span>
          <span v-else>{{ isSignUp ? 'Sign Up' : 'Sign In' }}</span>
        </button>
      </form>

      <!-- Toggle Sign Up / Sign In -->
      <div class="mt-4 text-center">
        <button
          @click="isSignUp = !isSignUp"
          class="text-godot-blue hover:underline text-sm"
        >
          {{ isSignUp ? 'Already have an account? Sign In' : "Don't have an account? Sign Up" }}
        </button>
      </div>

      <!-- OAuth Divider -->
      <div class="relative my-6">
        <div class="absolute inset-0 flex items-center">
          <div class="w-full border-t border-godot-border"></div>
        </div>
        <div class="relative flex justify-center text-sm">
          <span class="px-2 bg-godot-surface text-godot-muted">Or continue with</span>
        </div>
      </div>

      <!-- OAuth Buttons -->
      <div class="grid grid-cols-2 gap-3">
        <button
          @click="handleOAuth('github')"
          class="btn btn-secondary flex items-center justify-center gap-2"
        >
          <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
          </svg>
          GitHub
        </button>
        <button
          @click="handleOAuth('google')"
          class="btn btn-secondary flex items-center justify-center gap-2"
        >
          <svg class="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Google
        </button>
      </div>
    </div>
  </div>
</template>
