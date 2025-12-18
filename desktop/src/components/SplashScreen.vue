<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status?: string
}>()

const statusText = computed(() => props.status || 'Starting up...')
</script>

<template>
  <div class="splash-container">
    <div class="splash-content">
      <!-- Animated Logo -->
      <div class="logo-container">
        <!-- Pulse effect rings -->
        <div class="pulse-ring"></div>
        <div class="pulse-ring delay-1"></div>
        <!-- Actual Logo -->
        <img src="@/assets/icon.svg" alt="Godoty Logo" class="logo core" />
      </div>
      
      <!-- Title -->
      <h1 class="title">Godoty</h1>
      <p class="subtitle">AI Assistant</p>
      
      <!-- Loading indicator -->
      <div class="loading-bar">
        <div class="loading-progress"></div>
      </div>
      
      <!-- Status text -->
      <p class="status">{{ statusText }}</p>
    </div>
  </div>
</template>

<style scoped>
.splash-container {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  /* Use Godot-inspired dark theme gradient */
  background: linear-gradient(135deg, #202531 0%, #1a1e29 100%);
  z-index: 9999;
}

.splash-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
}

.logo-container {
  width: 120px;
  height: 120px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.logo {
  width: 80px;
  height: 80px;
  position: relative;
  z-index: 2;
  filter: drop-shadow(0 0 15px rgba(71, 140, 191, 0.3));
}

.pulse-ring {
  position: absolute;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 2px solid #478cbf;
  opacity: 0;
  animation: pulse 3s ease-out infinite;
  top: 0;
  left: 0;
}

.pulse-ring.delay-1 {
  animation-delay: 1s;
}

.core {
  animation: float 6s ease-in-out infinite alternate;
}

@keyframes pulse {
  0% {
    transform: scale(0.8);
    opacity: 0.5;
  }
  100% {
    transform: scale(1.5);
    opacity: 0;
  }
}

@keyframes float {
  0% {
    transform: translateY(0);
  }
  100% {
    transform: translateY(-5px);
  }
}

.title {
  font-size: 2.5rem;
  font-weight: 700;
  /* Using Godot Blue */
  color: #478cbf;
  margin: 0;
  letter-spacing: -0.02em;
  text-shadow: 0 0 20px rgba(71, 140, 191, 0.2);
}

.subtitle {
  font-size: 1rem;
  color: #9ca3af;
  margin: -1rem 0 0 0;
  font-weight: 400;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.loading-bar {
  width: 200px;
  height: 4px;
  background: #2d3546;
  border-radius: 2px;
  overflow: hidden;
  margin-top: 1rem;
}

.loading-progress {
  height: 100%;
  width: 40%;
  background: #478cbf;
  border-radius: 2px;
  animation: loading 1.5s ease-in-out infinite;
  box-shadow: 0 0 10px rgba(71, 140, 191, 0.5);
}

@keyframes loading {
  0% {
    transform: translateX(-100%);
  }
  50% {
    transform: translateX(200%);
  }
  100% {
    transform: translateX(-100%);
  }
}

.status {
  font-size: 0.875rem;
  color: #9ca3af;
  margin: 0;
  font-family: monospace;
  opacity: 0.8;
}
</style>

