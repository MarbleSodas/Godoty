<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useBrainStore } from '@/stores/brain'
import { onMounted } from 'vue'

const authStore = useAuthStore()
const brainStore = useBrainStore()

onMounted(async () => {
  // Initialize auth state
  await authStore.initialize()
  
  // Start the brain sidecar
  await brainStore.startBrain()
})
</script>

<template>
  <div class="h-screen w-screen flex flex-col overflow-hidden">
    <RouterView />
  </div>
</template>
