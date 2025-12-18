<script setup lang="ts">
import { RouterView, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useBrainStore } from '@/stores/brain'
import { onMounted, onBeforeUnmount } from 'vue'
import SplashScreen from '@/components/SplashScreen.vue'

const authStore = useAuthStore()
const brainStore = useBrainStore()
const router = useRouter()

onMounted(async () => {
  // Start the brain sidecar first (shows splash screen during this)
  await brainStore.startBrain()
  
  // Initialize auth state after brain is ready
  await authStore.initialize()
  
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

// Cleanup when app is closing
onBeforeUnmount(async () => {
  console.log('[App] Unmounting, stopping brain...')
  await brainStore.stopBrain()
})
</script>

<template>
  <!-- Show splash screen until brain is ready -->
  <SplashScreen 
    v-if="!brainStore.brainReady" 
    :status="brainStore.startupStatus" 
  />
  
  <!-- Main app content after brain is ready -->
  <div v-else class="h-screen w-screen flex flex-col overflow-hidden">
    <RouterView />
  </div>
</template>

