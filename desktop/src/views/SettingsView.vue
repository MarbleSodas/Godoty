<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useBrainStore } from '@/stores/brain'

interface IndexedVersion {
  version: string
  document_count: number
  size_bytes: number
}

const router = useRouter()
const authStore = useAuthStore()
const brainStore = useBrainStore()
const copySuccess = ref(false)

const indexedVersions = ref<IndexedVersion[]>([])
const deletingVersion = ref<string | null>(null)
const reindexingVersion = ref<string | null>(null)

// Check status on mount
brainStore.checkKnowledgeStatus()

async function handleSignOut() {
  await authStore.signOut()
  router.push('/login')
}

async function handleRegenerateKey() {
  await authStore.regenerateVirtualKey()
}

async function copyKeyToClipboard() {
  if (authStore.virtualKey) {
    await navigator.clipboard.writeText(authStore.virtualKey)
    copySuccess.value = true
    setTimeout(() => {
      copySuccess.value = false
    }, 2000)
  }
}

async function refreshIndexedVersions() {
  const result = await brainStore.listIndexedVersions()
  indexedVersions.value = result.versions
}

async function deleteVersion(version: string) {
  deletingVersion.value = version
  try {
    await brainStore.deleteIndexedVersion(version)
    await refreshIndexedVersions()
    brainStore.showToast(`Deleted Godot ${version} documentation`, 'success')
  } catch (e) {
    brainStore.showToast(`Failed to delete: ${(e as Error).message}`, 'error')
  } finally {
    deletingVersion.value = null
  }
}

async function reindexVersion(version: string) {
  reindexingVersion.value = version
  try {
    await brainStore.reindexVersion(version)
    brainStore.showToast(`Started reindexing Godot ${version} documentation`, 'info')
  } catch (e) {
    brainStore.showToast(`Failed to reindex: ${(e as Error).message}`, 'error')
  } finally {
    reindexingVersion.value = null
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

onMounted(() => {
  brainStore.checkKnowledgeStatus()
  refreshIndexedVersions()
})
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
    <div class="flex-1 p-8 overflow-y-auto bg-[#202531]">
      <h1 class="text-2xl font-bold mb-8 text-gray-200">Settings</h1>

      <!-- Account Section -->
      <section class="bg-[#1a1e29] border border-[#3b4458] rounded-lg p-6 mb-6">
        <h2 class="text-lg font-semibold mb-4 text-gray-200">Account</h2>
        
        <div v-if="authStore.user" class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-1">Email</label>
            <p class="text-gray-200">{{ authStore.user.email }}</p>
          </div>
          
          <div>
            <label class="block text-sm text-gray-400 mb-1">User ID</label>
            <p class="text-gray-200 font-mono text-sm">{{ authStore.user.id }}</p>
          </div>

          <button @click="handleSignOut" class="px-4 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors text-sm font-medium">
            Sign Out
          </button>
        </div>
      </section>

      <!-- Connection Section -->
      <section class="bg-[#1a1e29] border border-[#3b4458] rounded-lg p-6 mb-6">
        <h2 class="text-lg font-semibold mb-4 text-gray-200">Connection</h2>
        
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-1">Brain Server URL</label>
            <input
              type="text"
              value="ws://127.0.0.1:8000/ws/tauri"
              disabled
              class="w-full bg-[#202531] border border-[#3b4458] rounded-md px-3 py-2 text-gray-400 text-sm font-mono focus:outline-none"
            />
            <p class="text-xs text-gray-500 mt-1">The Python brain runs as a sidecar process</p>
          </div>
        </div>
      </section>

      <!-- Credits Section -->
      <section v-if="authStore.user" class="bg-[#1a1e29] border border-[#3b4458] rounded-lg p-6 mb-6">
        <h2 class="text-lg font-semibold mb-4 text-gray-200">Credits</h2>
        
        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <label class="block text-sm text-gray-400 mb-1">Available Credits</label>
              <p class="text-2xl font-bold text-green-400">{{ authStore.formattedRemainingCredits }}</p>
            </div>
            <button 
              @click="authStore.refreshCreditBalance()" 
              class="px-3 py-1.5 bg-[#3b4458] hover:bg-[#4a5568] text-gray-200 rounded-md transition-colors text-sm"
            >
              Refresh
            </button>
          </div>
          
          <div class="grid grid-cols-2 gap-4 text-sm">
            <div>
              <label class="block text-gray-400 mb-1">Total Budget</label>
              <p class="text-gray-200">{{ authStore.formattedMaxCredits }}</p>
            </div>
            <div>
              <label class="block text-gray-400 mb-1">Used</label>
              <p class="text-gray-200">{{ authStore.formattedUsedCredits }}</p>
            </div>
          </div>

          <button 
            @click="authStore.openPricingPage()" 
            class="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors text-sm font-medium"
          >
            Purchase More Credits
          </button>
        </div>
      </section>

      <!-- Developer Section -->
      <section v-if="authStore.user" class="bg-[#1a1e29] border border-[#3b4458] rounded-lg p-6 mb-6">
        <h2 class="text-lg font-semibold mb-4 text-gray-200">Developer</h2>
        
        <div class="space-y-4">
          <!-- Virtual Key Display -->
          <div>
            <label class="block text-sm text-gray-400 mb-1">Virtual API Key</label>
            <div class="flex items-center gap-2">
              <div class="flex-1 bg-[#202531] border border-[#3b4458] rounded-md px-3 py-2 font-mono text-sm text-gray-300 overflow-x-auto">
                <span v-if="authStore.maskedKey">{{ authStore.maskedKey }}</span>
                <span v-else class="text-gray-500">No key generated</span>
              </div>
              
              <!-- Toggle Visibility -->
              <button 
                v-if="authStore.virtualKey"
                @click="authStore.toggleKeyVisibility()" 
                class="px-3 py-2 bg-[#3b4458] hover:bg-[#4a5568] text-gray-200 rounded-md transition-colors text-sm"
                :title="authStore.showFullKey ? 'Hide key' : 'Show key'"
              >
                <svg v-if="authStore.showFullKey" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                  <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </button>
              
              <!-- Copy Button -->
              <button 
                v-if="authStore.virtualKey"
                @click="copyKeyToClipboard()" 
                class="px-3 py-2 bg-[#3b4458] hover:bg-[#4a5568] text-gray-200 rounded-md transition-colors text-sm"
                :class="{ 'bg-green-600': copySuccess }"
                :title="copySuccess ? 'Copied!' : 'Copy to clipboard'"
              >
                <svg v-if="copySuccess" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
                </svg>
              </button>
            </div>
            <p class="text-xs text-gray-500 mt-1">Use this key to access the LiteLLM API directly</p>
          </div>

          <!-- Key Status -->
          <div v-if="authStore.virtualKeyInfo" class="text-sm">
            <div class="flex items-center gap-2">
              <span class="w-2 h-2 rounded-full" :class="authStore.hasValidKey ? 'bg-green-500' : 'bg-red-500'"></span>
              <span class="text-gray-400">
                {{ authStore.hasValidKey ? 'Key is valid' : 'Key expired' }}
              </span>
            </div>
          </div>

          <!-- Regenerate Key Button -->
          <button 
            @click="handleRegenerateKey()" 
            :disabled="authStore.keyLoading"
            class="px-4 py-2 bg-amber-600 hover:bg-amber-700 disabled:bg-gray-600 text-white rounded-lg transition-colors text-sm font-medium"
          >
            <span v-if="authStore.keyLoading">Regenerating...</span>
            <span v-else>Regenerate Key</span>
          </button>
          <p class="text-xs text-gray-500">Generate a new API key. Your credits will remain unchanged.</p>

          <!-- Error Display -->
          <div v-if="authStore.keyError" class="text-red-400 text-sm bg-red-900/20 border border-red-800 rounded-md p-3">
            {{ authStore.keyError }}
          </div>
        </div>
      </section>

      <!-- Knowledge Base Section -->
      <section class="bg-[#1a1e29] border border-[#3b4458] rounded-lg p-6 mb-6">
        <h2 class="text-lg font-semibold mb-4 text-gray-200">Knowledge Base</h2>
        
        <div class="space-y-4">
          <!-- Current Status -->
          <div>
            <label class="block text-sm text-gray-400 mb-2">Current Documentation</label>
            <div class="flex items-center justify-between bg-[#202531] rounded-lg p-3">
              <div class="flex items-center gap-3">
                <span 
                  class="w-2.5 h-2.5 rounded-full"
                  :class="{
                    'bg-green-500': brainStore.knowledgeStatus.isIndexed && !brainStore.knowledgeStatus.isIndexing,
                    'bg-yellow-500 animate-pulse': brainStore.knowledgeStatus.isIndexing,
                    'bg-gray-500': !brainStore.knowledgeStatus.isIndexed && !brainStore.knowledgeStatus.isIndexing
                  }"
                ></span>
                <div>
                  <span class="text-gray-200">Godot {{ brainStore.knowledgeStatus.version }}</span>
                  <span 
                    class="ml-2 text-xs px-2 py-0.5 rounded-full"
                    :class="{
                      'bg-green-500/10 text-green-400': brainStore.knowledgeStatus.isIndexed && !brainStore.knowledgeStatus.isIndexing,
                      'bg-yellow-500/10 text-yellow-400': brainStore.knowledgeStatus.isIndexing,
                      'bg-gray-500/10 text-gray-400': !brainStore.knowledgeStatus.isIndexed && !brainStore.knowledgeStatus.isIndexing
                    }"
                  >
                    {{ brainStore.knowledgeStatus.isIndexing ? 'Indexing...' : (brainStore.knowledgeStatus.isIndexed ? 'Ready' : 'Not Loaded') }}
                  </span>
                </div>
                <span v-if="brainStore.knowledgeStatus.isIndexed && !brainStore.knowledgeStatus.isIndexing" class="text-xs text-gray-500">
                  {{ brainStore.knowledgeStatus.documentCount }} docs
                </span>
              </div>
              
              <button 
                @click="brainStore.reindexKnowledge()" 
                :disabled="brainStore.knowledgeStatus.isIndexing"
                class="px-3 py-1.5 bg-[#3b4458] hover:bg-[#4a5568] disabled:bg-[#2d3546] disabled:text-gray-500 text-gray-200 rounded-md transition-colors text-sm flex items-center gap-2"
              >
                <svg v-if="brainStore.knowledgeStatus.isIndexing" class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
                {{ brainStore.knowledgeStatus.isIndexing ? 'Indexing...' : 'Rebuild' }}
              </button>
            </div>
            
            <!-- Progress bar -->
            <div v-if="brainStore.knowledgeStatus.isIndexing && brainStore.knowledgeStatus.progress" class="mt-3">
              <div class="flex justify-between text-xs text-gray-400 mb-1">
                <span>{{ brainStore.knowledgeStatus.progress.phase === 'embedding' ? 'Embedding...' : 'Fetching Classes...' }}</span>
                <span>{{ brainStore.knowledgeStatus.progress.current }} / {{ brainStore.knowledgeStatus.progress.total }}</span>
              </div>
              <div class="w-full bg-[#2d3546] rounded-full h-1.5 overflow-hidden">
                <div 
                  class="bg-[#478cbf] h-full rounded-full transition-all duration-300 ease-out"
                  :style="{ width: `${(brainStore.knowledgeStatus.progress.current / brainStore.knowledgeStatus.progress.total) * 100}%` }"
                ></div>
              </div>
            </div>
          </div>
          
          <!-- Cached Versions -->
          <div>
            <div class="flex items-center justify-between mb-2">
              <label class="block text-sm text-gray-400">Cached Versions</label>
              <button 
                @click="refreshIndexedVersions()" 
                class="text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Refresh
              </button>
            </div>
            
            <div v-if="indexedVersions.length === 0" class="text-sm text-gray-500 bg-[#202531] rounded-lg p-3">
              No cached documentation found
            </div>
            
            <div v-else class="space-y-2">
              <div 
                v-for="v in indexedVersions" 
                :key="v.version"
                class="flex items-center justify-between bg-[#202531] rounded-lg p-3"
              >
                <div class="flex items-center gap-3">
                  <span class="text-gray-200">Godot {{ v.version }}</span>
                  <span class="text-xs text-gray-500">{{ v.document_count }} docs</span>
                  <span class="text-xs text-gray-500">{{ formatBytes(v.size_bytes) }}</span>
                </div>
                
                <div class="flex items-center gap-2">
                  <button 
                    @click="reindexVersion(v.version)"
                    :disabled="reindexingVersion === v.version || brainStore.knowledgeStatus.isIndexing"
                    class="px-2 py-1 text-xs bg-[#3b4458] hover:bg-[#4a5568] disabled:bg-[#2d3546] disabled:text-gray-500 text-gray-300 rounded transition-colors"
                  >
                    {{ reindexingVersion === v.version ? 'Rebuilding...' : 'Rebuild' }}
                  </button>
                  <button 
                    @click="deleteVersion(v.version)"
                    :disabled="deletingVersion === v.version"
                    class="px-2 py-1 text-xs bg-red-900/30 hover:bg-red-900/50 disabled:bg-[#2d3546] text-red-400 hover:text-red-300 disabled:text-gray-500 rounded transition-colors"
                  >
                    {{ deletingVersion === v.version ? 'Deleting...' : 'Delete' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
          
          <p class="text-xs text-gray-500">
            Documentation is automatically indexed when Godot connects. You can manually rebuild or delete cached versions.
          </p>
        </div>
      </section>

      <!-- About Section -->
      <section class="bg-[#1a1e29] border border-[#3b4458] rounded-lg p-6">
        <h2 class="text-lg font-semibold mb-4 text-gray-200">About</h2>
        
        <div class="space-y-2 text-sm text-gray-400">
          <p>Godoty v0.1.0</p>
          <p>AI-powered assistant for Godot game development</p>
        </div>
      </section>
    </div>
  </div>
</template>
