import "@opencode-ai/app/index.css"
import { ErrorBoundary, Show, lazy, type ParentProps } from "solid-js"
import { Router, Route, Navigate, HashRouter } from "@solidjs/router"
import { MetaProvider } from "@solidjs/meta"
import { Font } from "@opencode-ai/ui/components/font"
import { MarkedProvider } from "@opencode-ai/ui/context/marked"
import { DiffComponentProvider } from "@opencode-ai/ui/context/diff"
import { CodeComponentProvider } from "@opencode-ai/ui/context/code"
import { I18nProvider } from "@opencode-ai/ui/context"
import { Diff } from "@opencode-ai/ui/components/diff"
import { Code } from "@opencode-ai/ui/components/code"
import { ThemeProvider } from "@opencode-ai/ui/theme"
import { GlobalSyncProvider } from "@opencode-ai/app/context/global-sync"
import { PermissionProvider } from "@opencode-ai/app/context/permission"
import { LayoutProvider } from "@opencode-ai/app/context/layout"
import { GlobalSDKProvider } from "@opencode-ai/app/context/global-sdk"
import { normalizeServerUrl, ServerProvider, useServer } from "@opencode-ai/app/context/server"
import { SettingsProvider } from "@opencode-ai/app/context/settings"
import { TerminalProvider } from "@opencode-ai/app/context/terminal"
import { PromptProvider } from "@opencode-ai/app/context/prompt"
import { FileProvider } from "@opencode-ai/app/context/file"
import { CommentsProvider } from "@opencode-ai/app/context/comments"
import { NotificationProvider } from "@opencode-ai/app/context/notification"
import { ModelsProvider } from "@opencode-ai/app/context/models"
import { DialogProvider } from "@opencode-ai/ui/context/dialog"
import { CommandProvider } from "@opencode-ai/app/context/command"
import { LanguageProvider, useLanguage } from "@opencode-ai/app/context/language"
import { usePlatform } from "@opencode-ai/app/context/platform"
import { HighlightsProvider } from "@opencode-ai/app/context/highlights"
import Layout from "@opencode-ai/app/pages/layout"
import DirectoryLayout from "@opencode-ai/app/pages/directory-layout"
import { ErrorPage } from "./pages/error"
import { Suspense, JSX } from "solid-js"

const Home = lazy(() => import("@opencode-ai/app/pages/home"))
const Session = lazy(() => import("@opencode-ai/app/pages/session"))
const Loading = () => <div class="size-full bg-white text-black flex items-center justify-center">Loading App...</div>

function UiI18nBridge(props: ParentProps) {
  const language = useLanguage()
  return <I18nProvider value={{ locale: language.locale, t: language.t }}>{props.children}</I18nProvider>
}

declare global {
  interface Window {
    __OPENCODE__?: { updaterEnabled?: boolean; serverPassword?: string; deepLinks?: string[] }
  }
}

function MarkedProviderWithNativeParser(props: ParentProps) {
  const platform = usePlatform()
  return <MarkedProvider nativeParser={platform.parseMarkdown}>{props.children}</MarkedProvider>
}

export function AppBaseProviders(props: ParentProps) {
  return (
    <MetaProvider>
      <Font />
      <ThemeProvider>
        <LanguageProvider>
          <UiI18nBridge>
            <ErrorBoundary fallback={(error) => <ErrorPage error={error} />}>
              <DialogProvider>
                <MarkedProviderWithNativeParser>
                  <DiffComponentProvider component={Diff}>
                    <CodeComponentProvider component={Code}>{props.children}</CodeComponentProvider>
                  </DiffComponentProvider>
                </MarkedProviderWithNativeParser>
              </DialogProvider>
            </ErrorBoundary>
          </UiI18nBridge>
        </LanguageProvider>
      </ThemeProvider>
    </MetaProvider>
  )
}

function ServerKey(props: ParentProps) {
  const server = useServer()

  return (
    <Show when={server.url} fallback={
      <div class="flex items-center justify-center size-full bg-background-base">
        <span class="text-text-secondary">Loading...</span>
      </div>
    }>
      {props.children}
    </Show>
  )
}

export function AppInterface(props: { defaultUrl?: string; children?: JSX.Element }) {
  const platform = usePlatform()

  const stored = (() => {
    if (platform.platform !== "web") return
    const result = platform.getDefaultServerUrl?.()
    if (result instanceof Promise) return
    if (!result) return
    return normalizeServerUrl(result)
  })()

  const defaultServerUrl = () => {
    if (props.defaultUrl) return props.defaultUrl
    if (stored) return stored
    if (location.hostname.includes("opencode.ai")) return "http://localhost:4096"
    if (import.meta.env.DEV)
      return `http://${import.meta.env.VITE_OPENCODE_SERVER_HOST ?? "localhost"}:${import.meta.env.VITE_OPENCODE_SERVER_PORT ?? "4096"}`

    // In production Tauri builds, the sidecar runs on localhost:4096
    // window.location.origin would be tauri://localhost which is wrong
    return "http://localhost:4096"
  }

  return (
    <ServerProvider defaultUrl={defaultServerUrl()}>
      <ServerKey>
        <GlobalSDKProvider>
          <GlobalSyncProvider>
            <HashRouter
              root={(routerProps) => (
                <SettingsProvider>
                  <PermissionProvider>
                    <LayoutProvider>
                      <NotificationProvider>
                        <ModelsProvider>
                          <CommandProvider>
                            <HighlightsProvider>
                              <Layout>
                                {props.children}
                                {routerProps.children}
                              </Layout>
                            </HighlightsProvider>
                          </CommandProvider>
                        </ModelsProvider>
                      </NotificationProvider>
                    </LayoutProvider>
                  </PermissionProvider>
                </SettingsProvider>
              )}
            >
              <Route
                path="/"
                component={() => (
                  <Suspense fallback={<Loading />}>
                    <Home />
                  </Suspense>
                )}
              />
              <Route path="*" component={() => <div class="p-10 text-red-500 font-bold">404: {location.href}</div>} />
              <Route path="/:dir" component={DirectoryLayout}>
                <Route path="/" component={() => <Navigate href="session" />} />
                <Route
                  path="/session/:id?"
                  component={(p) => (
                    <Show when={p.params.id ?? "new"}>
                      <TerminalProvider>
                        <FileProvider>
                          <PromptProvider>
                            <CommentsProvider>
                              <Suspense fallback={<Loading />}>
                                <Session />
                              </Suspense>
                            </CommentsProvider>
                          </PromptProvider>
                        </FileProvider>
                      </TerminalProvider>
                    </Show>
                  )}
                />
              </Route>
            </HashRouter>
          </GlobalSyncProvider>
        </GlobalSDKProvider>
      </ServerKey>
    </ServerProvider>
  )
}
