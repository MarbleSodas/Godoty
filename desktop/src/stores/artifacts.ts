import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Artifact {
    id: string
    title: string
    content: string
    language: string
    lineCount: number
}

export const useArtifactsStore = defineStore('artifacts', () => {
    const isOpen = ref(false)
    const currentArtifact = ref<Artifact | null>(null)

    // Registry of all artifacts from current messages
    const artifacts = ref<Map<string, Artifact>>(new Map())

    /**
     * Register an artifact from a code block
     */
    function registerArtifact(artifact: Artifact) {
        artifacts.value.set(artifact.id, artifact)
    }

    /**
     * Open the artifact panel with specific content
     */
    function openArtifact(id: string) {
        const artifact = artifacts.value.get(id)
        if (artifact) {
            currentArtifact.value = artifact
            isOpen.value = true
        }
    }

    /**
     * Close the artifact panel
     */
    function closeArtifact() {
        isOpen.value = false
        // Keep currentArtifact for smooth close animation
        setTimeout(() => {
            if (!isOpen.value) {
                currentArtifact.value = null
            }
        }, 300)
    }

    /**
     * Clear all artifacts (on session change)
     */
    function clearArtifacts() {
        artifacts.value.clear()
        currentArtifact.value = null
        isOpen.value = false
    }

    /**
     * Copy artifact content to clipboard
     */
    async function copyToClipboard(content: string): Promise<boolean> {
        try {
            await navigator.clipboard.writeText(content)
            return true
        } catch (e) {
            console.error('Failed to copy:', e)
            return false
        }
    }

    return {
        isOpen,
        currentArtifact,
        artifacts: computed(() => artifacts.value),
        registerArtifact,
        openArtifact,
        closeArtifact,
        clearArtifacts,
        copyToClipboard,
    }
})
