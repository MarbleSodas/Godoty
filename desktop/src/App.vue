<script setup lang="ts">
import { RouterView, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useBrainStore } from '@/stores/brain'
import { onMounted } from 'vue'

const authStore = useAuthStore()
const brainStore = useBrainStore()
const router = useRouter()

onMounted(async () => {
  // Initialize auth state
  await authStore.initialize()
  
  // Start the brain sidecar
  await brainStore.startBrain()
  
  // Listen for deep links (e.g. auth callbacks)
  // We use the dynamic import to avoid SSR issues if any, though here it's SPA
  const { onOpenUrl } = await import('@tauri-apps/plugin-deep-link')
  
  await onOpenUrl(async (urls) => {
    console.log('Deep links received:', urls)
    for (const url of urls) {
      if (url.startsWith('godoty://')) {
        await authStore.handleDeepLink(url)
        
        // Navigate to main page if successfully authenticated
        if (authStore.isAuthenticated) {
          console.log('Deep link auth successful, navigating to main')
          router.push('/')
        }
      }
    }
  })
})
</script>

<template>
  <div class="h-screen w-screen flex flex-col overflow-hidden">
    <RouterView />
  </div>
</template>
