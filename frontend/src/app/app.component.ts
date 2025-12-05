import { Component, signal, ViewChild, ElementRef, AfterViewChecked, ChangeDetectionStrategy, model, OnInit, inject, EffectRef, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService, Session, Message as ServiceMessage, ToolCall as ServiceToolCall } from './services/chat.service';
import { DesktopService, GodotStatus } from './services/desktop.service';
import { DocumentationService, DocumentationStatus, RebuildProgress } from './services/documentation.service';
import { catchError, of, switchMap, tap } from 'rxjs';

// --- Interfaces ---

interface ToolCall {
  toolName: string;
  toolUseId?: string;  // Add unique identifier
  input: string;
  output?: string;
  status: 'pending' | 'success' | 'error';
  error?: string;      // Add error message field
}

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  reasoning?: string;
  toolCalls?: ToolCall[];
  isStreaming?: boolean;
  chunks?: string[];
  error?: string;
  metrics?: {
    total_tokens: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost: number;
    model_id: string;
  };
}

interface Metrics {
  latency: number;
  tokensPerSec: number;
}

// --- Main App Component ---

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="flex h-screen w-full bg-[#202531] text-gray-200 font-sans overflow-hidden selection:bg-[#478cbf] selection:text-white">
      
      <!-- Sidebar -->
      <aside 
        class="flex-shrink-0 bg-[#1a1e29] border-r border-[#2d3546] transition-all duration-300 ease-in-out flex flex-col"
        [class.w-64]="sidebarOpen()"
        [class.w-0]="!sidebarOpen()"
        [class.overflow-hidden]="!sidebarOpen()"
      >
        <div class="p-4 flex items-center justify-between border-b border-[#2d3546]">
          <div class="flex items-center space-x-2 font-bold text-[#478cbf]">
            <!-- Godot-like Icon -->
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-6 h-6">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/> 
              <circle cx="9" cy="13" r="1.5" />
              <circle cx="15" cy="13" r="1.5" />
            </svg>
            <span>GODOTY</span>
          </div>
          <div class="flex items-center gap-1">
            <button (click)="openSettings()" class="p-1.5 hover:bg-[#2d3546] rounded-md transition-colors text-gray-400 hover:text-white" title="Settings">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>
            <button (click)="createNewSession()" class="p-1.5 hover:bg-[#2d3546] rounded-md transition-colors text-gray-400 hover:text-white" title="New Chat">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
              </svg>
            </button>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto py-2">
          <div class="px-4 pb-2 text-xs font-semibold text-gray-500 uppercase tracking-wider">History</div>
          @for (session of sessions(); track session.id) {
            <div
              (click)="selectSession(session.id)"
              (keydown.enter)="selectSession(session.id)"
              (keydown.space)="selectSession(session.id); $event.preventDefault()"
              role="button"
              tabindex="0"
              [attr.aria-label]="'Select session: ' + session.title"
              class="relative w-full text-left px-4 py-3 text-sm hover:bg-[#2d3546] transition-colors border-l-2 flex justify-between items-center group cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#478cbf]/50"
              [class.border-[#478cbf]]="activeSessionId() === session.id"
              [class.bg-[#262c3b]]="activeSessionId() === session.id"
              [class.text-white]="activeSessionId() === session.id"
              [class.text-gray-400]="activeSessionId() !== session.id"
              [class.border-transparent]="activeSessionId() !== session.id"
            >
              <span class="flex-1 truncate">
                {{ session.title }}
              </span>
              <button
                (click)="deleteSession(session.id, $event)"
                class="opacity-0 group-hover:opacity-100 transition-opacity p-2 hover:bg-red-500/10 rounded"
                title="Delete session"
                aria-label="Delete session"
              >
                🗑️
              </button>
            </div>
          }
        </div>
        
        <!--
        <div class="p-4 border-t border-[#2d3546] flex items-center space-x-3">
          <div class="w-8 h-8 rounded-full bg-gradient-to-tr from-[#478cbf] to-cyan-400 flex items-center justify-center text-xs font-bold text-white">
            GD
          </div>
          <div class="text-sm">
            <div class="font-medium text-gray-200">GameDev User</div>
            <div class="text-xs text-gray-500">Pro Plan</div>
          </div>
        </div>
        -->
      </aside>

      <!-- Main Content -->
      <main class="flex-1 flex flex-col relative min-w-0">
        
        <!-- Header -->
        <header class="h-14 border-b border-[#2d3546] bg-[#202531]/95 backdrop-blur flex items-center justify-between px-4 z-10 sticky top-0">
          <div class="flex items-center">
            <button (click)="toggleSidebar()" class="mr-3 p-2 hover:bg-[#2d3546] rounded-md text-gray-400 hover:text-white transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              </svg>
            </button>
            <div class="flex flex-col">
              <span class="font-semibold text-gray-200 text-sm">
                {{ godotStatus()?.project_settings?.name || 'Godoty 4.3 Assistant' }}
              </span>
              <span class="text-[10px] flex items-center gap-1" [class.text-[#478cbf]]="isGodotConnected()" [class.text-red-500]="!isGodotConnected()">
                <span class="w-1.5 h-1.5 rounded-full animate-pulse" [class.bg-green-500]="isGodotConnected()" [class.bg-red-500]="!isGodotConnected()"></span>
                {{ isGodotConnected() ? 'Online' : 'Offline' }} 
                @if(godotStatus()?.godot_version) {
                   - {{ godotStatus()?.godot_version }}
                }
              </span>
            </div>
          </div>

          <!-- Metrics Panel -->
          <div class="flex items-center gap-4 text-xs font-mono text-gray-500 bg-[#1a1e29] px-3 py-1.5 rounded border border-[#2d3546]">
            <div class="flex items-center gap-1.5" title="Session Cost">
              <span class="text-green-500">$</span>
              <span>{{ sessionMetrics().total_cost | number:'1.4-4' }}</span>
            </div>
            <div class="w-px h-3 bg-[#2d3546]"></div>
            <div class="flex items-center gap-1.5" title="Session Tokens">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
                <path fill-rule="evenodd" d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z" clip-rule="evenodd" />
              </svg>
              <span>{{ sessionMetrics().total_tokens | number:'1.0-0' }}</span>
            </div>
          </div>
        </header>

        <!-- Chat Area -->
        <div class="flex-1 overflow-y-auto p-4 scroll-smooth" #scrollContainer>
          <div class="max-w-3xl mx-auto space-y-6 pb-20">
            
            <!-- Empty State -->
            @if (messages().length === 0) {
              <div class="flex flex-col items-center justify-center h-full py-20 opacity-50 select-none">
                <div class="w-16 h-16 bg-[#2d3546] rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-[#478cbf]/10">
                   <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-8 h-8 text-[#478cbf]">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/> 
                  </svg>
                </div>
                <h2 class="text-xl font-medium text-gray-300">How can I help with your Godot project?</h2>
                <p class="text-sm text-gray-500 mt-2">Ask about GDScript, shaders, or scene composition.</p>
              </div>
            }

            @for (msg of messages(); track msg.id) {
              <!-- User Message -->
              @if (msg.role === 'user' && msg.content.trim()) {
                <div class="flex justify-end animate-fade-in-up">
                  <div class="bg-[#2d3546] text-gray-100 px-4 py-3 rounded-2xl rounded-tr-sm max-w-[85%] shadow-sm border border-[#3b4458]">
                    <div class="text-sm whitespace-pre-wrap leading-relaxed">{{ msg.content }}</div>
                  </div>
                </div>
              }

              <!-- Assistant Message -->
              @if (msg.role === 'assistant' && (msg.content.trim() || msg.reasoning || (msg.toolCalls && msg.toolCalls.length > 0))) {
                <div class="flex gap-4 animate-fade-in pr-4">
                  <div class="flex-shrink-0 mt-1">
                    <div class="w-8 h-8 rounded-lg bg-[#478cbf] flex items-center justify-center shadow-lg shadow-blue-500/20">
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="white" class="w-5 h-5">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8 8zm-1-13h2v6h-2zm0 8h2v2h-2z"/> 
                        <circle cx="9" cy="13" r="1.5" />
                        <circle cx="15" cy="13" r="1.5" />
                      </svg>
                    </div>
                  </div>
                  
                  <div class="flex-1 space-y-4 min-w-0">
                    
                    <!-- Reasoning Block -->
                    @if (msg.reasoning) {
                      <div class="group">
                        <details [open]="msg.isStreaming" class="bg-[#1a1e29]/50 border-l-2 border-[#478cbf]/30 rounded-r pl-3 py-1 open:bg-[#1a1e29] open:py-2 transition-all">
                          <summary class="text-xs font-mono text-[#478cbf] cursor-pointer hover:text-blue-300 select-none flex items-center gap-2 outline-none">
                            <span class="opacity-70 group-hover:opacity-100 transition-opacity">thought process</span>
                            @if (msg.isStreaming && !msg.content) {
                                <span class="animate-pulse w-1.5 h-1.5 bg-[#478cbf] rounded-full"></span>
                            }
                          </summary>
                          <div class="mt-2 text-xs text-gray-400 font-mono leading-relaxed whitespace-pre-wrap animate-fade-in pl-1">
                            {{ msg.reasoning }}
                          </div>
                        </details>
                      </div>
                    }

                    <!-- Tool Calls -->
                    @if (msg.toolCalls && msg.toolCalls.length > 0) {
                        @for (tool of msg.toolCalls; track tool) {
                            <div class="my-2 border border-[#3b4458] rounded-md bg-[#161922] overflow-hidden font-mono text-xs shadow-sm">
                                <div class="bg-[#1f2430] px-3 py-2 flex items-center justify-between border-b border-[#2d3546]">
                                    <div class="flex items-center gap-2 text-gray-300">
                                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 text-[#478cbf]">
                                            <path stroke-linecap="round" stroke-linejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 18" />
                                        </svg>
                                        <span>Called: <span class="text-[#478cbf]">{{ tool.toolName }}</span></span>
                                    </div>
                                    @if (tool.status === 'pending') {
                                        <div class="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded text-[10px] uppercase font-bold bg-yellow-900 text-yellow-200">
                                            <svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                            </svg>
                                            <span>Executing</span>
                                        </div>
                                    } @else {
                                        <span class="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold"
                                            [class.bg-green-900]="tool.status === 'success'"
                                            [class.text-green-200]="tool.status === 'success'"
                                            [class.bg-red-900]="tool.status === 'error'"
                                            [class.text-red-200]="tool.status === 'error'">
                                            {{ tool.status }}
                                        </span>
                                    }
                                </div>
                                <div class="p-3 text-gray-400">
                                    <div class="mb-1 text-gray-500 select-none">// Input</div>
                                    <div class="mb-2 text-[#a5b6cf] whitespace-pre-wrap">{{ tool.input }}</div>
                                    @if (tool.output) {
                                        <div class="mt-2 pt-2 border-t border-[#2d3546]">
                                            <div class="mb-1 text-gray-500 select-none">// Output</div>
                                            <div class="text-[#89ca78] whitespace-pre-wrap">{{ tool.output }}</div>
                                        </div>
                                    }
                                    @if (tool.error) {
                                        <div class="mt-2 pt-2 border-t border-[#2d3546]">
                                            <div class="mb-1 text-red-400 select-none">// Error</div>
                                            <div class="text-red-300 whitespace-pre-wrap">{{ tool.error }}</div>
                                        </div>
                                    }
                                </div>
                            </div>
                        }
                    }

                    <!-- Main Content -->
                    <div class="prose prose-invert prose-sm max-w-none text-gray-300 leading-relaxed whitespace-pre-wrap">
                      @if (msg.isStreaming && msg.chunks) {
                         @for (chunk of msg.chunks; track $index) {
                           <span class="relative animate-fade-in-up">{{ chunk }}</span>
                         }
                      } @else {
                         {{ msg.content }}
                      }
                      @if (msg.isStreaming && !msg.reasoning) {
                        <span class="inline-block w-1.5 h-4 bg-[#478cbf] align-middle ml-0.5 animate-pulse"></span>
                      }
                    </div>

                  </div>
                </div>
              }
            }
          </div>
        </div>

        <!-- Input Area -->
        <div class="p-4 bg-[#202531]">
          @if (!chatReady()) {
            <!-- Disabled State Message -->
            <div class="max-w-3xl mx-auto text-center py-4 bg-[#2d3546] rounded-xl border border-[#3b4458]">
              <p class="text-gray-400 text-sm">{{ chatDisabledMessage() }}</p>
              <button (click)="openSettings()" class="text-[#478cbf] hover:underline text-sm mt-2">
                Open Settings
              </button>
            </div>
          } @else {
            <div class="max-w-3xl mx-auto flex items-end gap-2 bg-[#2d3546] rounded-xl shadow-lg border border-[#3b4458] focus-within:border-[#478cbf] focus-within:ring-1 focus-within:ring-[#478cbf]/50 transition-all duration-200 p-2">
              
              <textarea
                #messageInput
                [(ngModel)]="currentInput"
                (keydown.enter)="$event.preventDefault(); sendMessage()"
                placeholder="Ask Godoty a question..."
                class="flex-1 bg-transparent text-gray-200 placeholder-gray-500 text-sm px-4 py-3 rounded-xl focus:outline-none resize-none max-h-48 overflow-y-auto"
                rows="1"
                (input)="autoResize($event.target)"
              ></textarea>

              @if (isGenerating()) {
                <!-- Stop button when generating -->
                <button
                  (click)="stopGeneration()"
                  class="p-3 rounded-lg bg-red-500 text-white hover:bg-red-600 transition-all flex-shrink-0"
                  title="Stop generation"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
                    <path d="M5.25 3A2.25 2.25 0 003 5.25v9.5A2.25 2.25 0 005.25 17h9.5A2.25 2.25 0 0017 14.75v-9.5A2.25 2.25 0 0014.75 3h-9.5z" />
                  </svg>
                </button>
              } @else {
                <!-- Send button when not generating -->
                <button
                  (click)="sendMessage()"
                  [disabled]="!currentInput()"
                  class="p-3 rounded-lg bg-[#478cbf] text-white hover:bg-[#367fa9] disabled:opacity-50 disabled:bg-transparent disabled:text-gray-500 transition-all flex-shrink-0"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
                    <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A2 2 0 005.635 9.75h5.736a.75.75 0 010 1.5H5.636a2 2 0 00-1.942 1.586l-1.414 4.925a.75.75 0 00.826.95 28.89 28.89 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
                  </svg>
                </button>
              }
            </div>
          }
          <div class="text-center text-[10px] text-gray-600 mt-2 font-mono">
            Godoty can make mistakes. Check generated code in the Godot docs.
          </div>
        </div>

      </main>
    </div>
    <!-- Settings Modal -->
    @if (settingsOpen()) {
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
        <div class="bg-[#1a1e29] border border-[#2d3546] rounded-xl shadow-2xl w-full max-w-md overflow-hidden" (click)="$event.stopPropagation()">
          <!-- Modal Header -->
          <div class="px-6 py-4 border-b border-[#2d3546] flex justify-between items-center bg-[#202531]">
            <h3 class="text-lg font-semibold text-gray-200">Settings</h3>
            <button (click)="closeSettings()" class="text-gray-500 hover:text-white transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          
          <!-- Modal Body -->
          <div class="p-6 space-y-4">
            <!-- API Key Input -->
            <div class="space-y-2">
              <label class="block text-xs font-medium text-gray-400 uppercase tracking-wider">OpenRouter API Key</label>
              <input 
                type="password" 
                [(ngModel)]="settingsForm.openrouter_api_key" 
                placeholder="sk-or-..." 
                class="w-full bg-[#161922] border border-[#2d3546] rounded-lg px-4 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-[#478cbf] focus:ring-1 focus:ring-[#478cbf] transition-all placeholder-gray-600"
              >
              <p class="text-[10px] text-gray-500">Required for accessing models via OpenRouter.</p>
            </div>

            <!-- Model Selection -->
            <div class="space-y-2">
              <label class="block text-xs font-medium text-gray-400 uppercase tracking-wider">Model ID</label>
              <div class="relative">
                 <input 
                  type="text" 
                  [(ngModel)]="settingsForm.model_id" 
                  list="model-options"
                  placeholder="e.g., x-ai/grok-4.1-fast:free"
                  class="w-full bg-[#161922] border border-[#2d3546] rounded-lg px-4 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-[#478cbf] focus:ring-1 focus:ring-[#478cbf] transition-all placeholder-gray-600"
                >
                <datalist id="model-options">
                  <option value="anthropic/claude-opus-4.5"></option>
                  <option value="google/gemini-3-pro-preview"></option>
                  <option value="z-ai/glm-4.6"></option>
                  <option value="minimax/minimax-m2"></option>
                  <option value="anthropic/claude-haiku-4.5"></option>
                  <option value="deepseek/deepseek-v3.2"></option>
                  <option value="x-ai/grok-code-fast-1"></option>
                  <option value="anthropic/claude-sonnet-4.5"></option>
                </datalist>
              </div>
              <p class="text-[10px] text-gray-500">Specify the model ID to use for generation.</p>
            </div>

            <!-- Godot Documentation Section -->
            <div class="space-y-2">
              <label class="block text-xs font-medium text-gray-400 uppercase tracking-wider">Godot Documentation Database</label>

              <!-- Godot Version Info -->
              <div class="bg-[#161922] border border-[#2d3546] rounded-lg p-2 text-xs">
                <div class="flex items-center justify-between mb-1">
                  <span class="text-gray-400">Built Version:</span>
                  @if (documentationStatus(); as status) {
                    @if (status.godot_version) {
                      <span class="text-[#478cbf] font-medium">{{ status.godot_version }}</span>
                    } @else {
                      <span class="text-gray-500">Not built</span>
                    }
                  } @else {
                    <span class="text-gray-500">Loading...</span>
                  }
                </div>
                <div class="text-[10px] text-gray-500">
                  💡 Rebuild uses version from connected Godot editor, or defaults to 4.5.1-stable
                </div>
              </div>

              <!-- Status Display -->
              <div class="bg-[#161922] border border-[#2d3546] rounded-lg p-3">
                @if (documentationStatus(); as status) {
                  <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-2">
                      <span class="text-sm">
                        @switch (status?.status) {
                          @case ('not_built') {
                            <span class="text-gray-400">📚 Not Built</span>
                          }
                          @case ('building') {
                            <span class="text-yellow-400">🔄 Building...</span>
                          }
                          @case ('completed') {
                            <span class="text-green-400">✅ Ready</span>
                          }
                          @case ('error') {
                            <span class="text-red-400">❌ Error</span>
                          }
                        }
                      </span>
                      @if (status?.build_timestamp && status?.status === 'completed') {
                        <span class="text-xs text-gray-500">
                          Built: {{formatDate(status.build_timestamp!)}}
                        </span>
                      }
                    </div>
                    @if (status?.size_mb) {
                      <span class="text-xs text-gray-500">{{status.size_mb}} MB</span>
                    }
                  </div>

                  @if (status?.error_message) {
                    <p class="text-xs text-red-400 mt-2">{{status.error_message}}</p>
                  }
                } @else {
                  <span class="text-sm text-gray-500">Loading status...</span>
                }
              </div>

              <!-- Rebuild Button -->
              <button
                (click)="rebuildDocumentation()"
                  class="w-full bg-[#478cbf] hover:bg-[#367fa9] disabled:bg-gray-600 disabled:cursor-not-allowed text-white text-sm font-medium py-2 px-4 rounded-lg transition-colors flex items-center justify-center space-x-2"
              >
                @if (isRebuilding()) {
                  <svg class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span>Rebuilding...</span>
                } @else {
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                  </svg>
                  <span>Rebuild Documentation</span>
                }
              </button>

              <!-- Progress Bar -->
              @if (rebuildProgress(); as progress) {
                <div class="mt-2">
                  <div class="flex justify-between text-xs text-gray-400 mb-1">
                    <span>{{progress?.message}}</span>
                    <span>{{progress?.progress}}%</span>
                  </div>
                  <div class="w-full bg-gray-700 rounded-full h-2">
                    <div
                      class="bg-[#478cbf] h-2 rounded-full transition-all duration-300"
                      [style.width.%]="progress?.progress"
                    ></div>
                  </div>
                </div>
              }
            </div>
          </div>

          <!-- Modal Footer -->
          <div class="px-6 py-4 border-t border-[#2d3546] bg-[#202531] flex justify-end gap-3">
            <button (click)="closeSettings()" class="px-4 py-2 rounded-lg text-sm font-medium text-gray-400 hover:text-white hover:bg-[#2d3546] transition-colors">Cancel</button>
            <button (click)="saveSettings()" class="px-4 py-2 rounded-lg text-sm font-medium bg-[#478cbf] text-white hover:bg-[#367fa9] transition-colors shadow-lg shadow-blue-500/20">Save Changes</button>
          </div>
        </div>
      </div>
    }
  `,
  styles: [`
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #3b4458; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #4b556b; }
    
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    @keyframes fadeInUp { from { opacity: 0; top: 8px; } to { opacity: 1; top: 0; } }
    .animate-fade-in { animation: fadeIn 0.3s ease-out forwards; }
    .animate-fade-in-up { animation: fadeInUp 0.3s ease-out forwards; }
  `]
})
export class App implements OnInit, AfterViewChecked {
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;
  @ViewChild('messageInput') private messageInput!: ElementRef;

  private chatService = inject(ChatService);
  private desktopService = inject(DesktopService);
  private documentationService = inject(DocumentationService);

  sidebarOpen = signal(true);
  currentInput = signal('');
  isGenerating = signal(false);
  private currentAbortController: AbortController | null = null;
  activeSessionId = signal<string | null>(null);
  isDraftMode = signal(false);

  // Settings State
  settingsOpen = signal(false);
  settingsForm = { model_id: '', openrouter_api_key: '' };

  // Documentation State
  documentationStatus = signal<DocumentationStatus | null>(null);
  isRebuilding = signal(false);
  rebuildProgress = signal<RebuildProgress | null>(null);

  metrics = signal<Metrics>({
    latency: 0,
    tokensPerSec: 0,
  });

  sessions = signal<Session[]>([]);
  messages = signal<Message[]>([]);
  godotStatus = signal<GodotStatus | null>(null);
  isGodotConnected = signal(false);

  // Chat Readiness State
  chatReady = signal(false);
  chatDisabledMessage = signal('');

  sessionMetrics = signal<{ total_tokens: number; total_cost: number }>({
    total_tokens: 0,
    total_cost: 0
  });

  constructor() {
    // Effect to scroll to bottom when messages change
    effect(() => {
      this.messages();
      setTimeout(() => this.scrollToBottom(), 0);
    });
  }

  ngOnInit() {
    // Start in draft mode optimistically
    this.isDraftMode.set(true);

    this.loadSessions();

    // Subscribe to Godot Status
    this.desktopService.streamGodotStatus().subscribe(status => {
      this.godotStatus.set(status);
      this.isGodotConnected.set(status.state === 'connected');

      // If we have a project path, tell chat service
      if (status.project_path) {
        this.chatService.setProjectPath(status.project_path);
      }

      // Re-check chat readiness when Godot status changes
      this.checkChatReadiness();
    });

    // Subscribe to Project Metrics
    this.chatService.projectMetrics$.subscribe(metrics => {
      // Update global metrics if needed, or just use per-message metrics
    });

    // Initial chat readiness check
    this.checkChatReadiness();

    // Poll chat readiness every 5 seconds
    setInterval(() => this.checkChatReadiness(), 5000);
  }

  /**
   * Check if chat is ready (Godot connected + API key configured)
   */
  private checkChatReadiness() {
    this.chatService.checkChatReady().subscribe({
      next: (result) => {
        this.chatReady.set(result.ready);
        this.chatDisabledMessage.set(result.ready ? '' : result.message);
      },
      error: () => {
        this.chatReady.set(false);
        this.chatDisabledMessage.set('Unable to connect to backend');
      }
    });
  }

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  loadSessions() {
    this.chatService.listSessions().subscribe(sessions => {
      this.sessions.set(sessions);

      // Exit draft mode if sessions exist
      if (sessions.length > 0) {
        this.isDraftMode.set(false);

        // Auto-select first session if no active session
        if (!this.activeSessionId()) {
          this.selectSession(sessions[0].id);
        }
      }
      // If sessions.length === 0, stays in draft mode (already set in ngOnInit)
    });
  }

  openSettings() {
    this.chatService.getAgentConfig().subscribe({
      next: (response) => {
        if (response.status === 'success' && response.config) {
          const config = response.config.model_config || {};

          this.settingsForm = {
            model_id: config.model_id || '',
            openrouter_api_key: '' // Don't show existing key for security
          };
        }
        this.settingsOpen.set(true);

        // Load documentation status
        this.loadDocumentationStatus();
      },
      error: (err) => {
        console.error('Failed to load config:', err);
        // Open anyway with defaults
        this.settingsOpen.set(true);

        // Load documentation status even on error
        this.loadDocumentationStatus();
      }
    });
  }

  closeSettings() {
    this.settingsOpen.set(false);
    this.resetRebuildState();
  }

  saveSettings() {
    const config = this.settingsForm;

    // Validate model_id format
    if (config.model_id && !config.model_id.includes('/')) {
      alert('Please enter a valid model ID (e.g., "anthropic/claude-opus-4.5")');
      return;
    }

    const updatePayload: any = {
      model_id: config.model_id
    };

    if (config.openrouter_api_key) {
      updatePayload.openrouter_api_key = config.openrouter_api_key;
    }

    this.chatService.updateAgentConfig(updatePayload).subscribe({
      next: (response) => {
        this.closeSettings();
        // Show success feedback
        alert('Settings saved successfully!');
      },
      error: (err) => {
        console.error('Failed to save settings:', err);
        const errorMessage = err.error?.detail || err.message || 'Unknown error occurred';
        alert(`Failed to save settings: ${errorMessage}`);
      }
    });
  }

  /**
   * Load documentation status when opening settings
   */
  private loadDocumentationStatus() {
    this.documentationService.getDocumentationStatus().subscribe({
      next: (status) => {
        this.documentationStatus.set(status);
        this.documentationService.updateStatus(status);
      },
      error: (error) => {
        console.error('Failed to load documentation status:', error);
        this.documentationStatus.set({
          success: false,
          status: 'error',
          database_exists: false,
          message: 'Failed to load status',
          error_message: error.message
        });
      }
    });
  }

  /**
   * Rebuild documentation database
   */
  rebuildDocumentation() {
    // Non-blocking: allow multiple requests, but show busy state during the actual API call
    if (this.isRebuilding()) return;

    this.rebuildProgress.set({
      stage: 'starting',
      progress: 0,
      message: 'Starting rebuild in background...'
    });

    // Call rebuild without version parameter - it will auto-detect from connected Godot editor
    this.documentationService.rebuildDocumentation().subscribe({
      next: (response) => {
        if (response.status === 'started') {
          this.rebuildProgress.set({
            stage: 'running',
            progress: 10,
            message: `Rebuild started in background (${response.estimated_time})`
          });

          // Start polling for rebuild status
          this.startRebuildStatusPolling();
        } else {
          // Handle error starting rebuild
          this.rebuildProgress.set({
            stage: 'error',
            progress: 0,
            message: 'Failed to start rebuild',
            error: response.error
          });

          setTimeout(() => {
            this.resetRebuildState();
          }, 5000);
        }
      },
      error: (error) => {
        // Handle API error
        this.rebuildProgress.set({
          stage: 'error',
          progress: 0,
          message: 'API error',
          error: error.message
        });

        setTimeout(() => {
          this.resetRebuildState();
        }, 5000);
      }
    });
  }

  private startRebuildStatusPolling() {
    // Poll every 1 second for rebuild status (more frequent for smoother progress)
    const pollInterval = setInterval(() => {
      this.documentationService.getRebuildStatus().subscribe({
        next: (status: any) => {
          if (status.running) {
            // Use actual progress from backend
            const progress = status.progress || 0;
            const message = status.message || 'Rebuilding documentation...';
            const filesInfo = status.files_total > 0
              ? ` (${status.files_processed}/${status.files_total})`
              : '';

            this.rebuildProgress.set({
              stage: status.stage || 'running',
              progress: progress,
              message: message + filesInfo
            });
          } else if (status.error) {
            // Rebuild failed
            clearInterval(pollInterval);
            this.rebuildProgress.set({
              stage: 'error',
              progress: 0,
              message: status.message || 'Rebuild failed',
              error: status.error
            });

            setTimeout(() => {
              this.resetRebuildState();
            }, 5000);
          } else {
            // Rebuild completed
            clearInterval(pollInterval);
            this.rebuildProgress.set({
              stage: 'completed',
              progress: 100,
              message: status.message || 'Documentation rebuild completed!'
            });

            // Reload documentation status after delay
            setTimeout(() => {
              this.loadDocumentationStatus();
              this.resetRebuildState();
            }, 2000);
          }
        },
        error: (error) => {
          clearInterval(pollInterval);
          this.rebuildProgress.set({
            stage: 'error',
            progress: 0,
            message: 'Status check failed',
            error: error.message
          });

          setTimeout(() => {
            this.resetRebuildState();
          }, 5000);
        }
      });
    }, 1000);
  }

  /**
   * Reset rebuild state
   */
  private resetRebuildState() {
    this.rebuildProgress.set(null);
    this.documentationService.resetRebuildState();
  }

  /**
   * Format date for display
   */
  formatDate(dateString: string): string {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }

  selectSession(sessionId: string) {
    this.activeSessionId.set(sessionId);
    this.messages.set([]); // Clear current messages
    this.isDraftMode.set(false); // Exit draft mode when selecting a session

    this.chatService.getSession(sessionId).subscribe(sessionData => {
      // Assuming sessionData contains messages. If not, we might need another endpoint or the data structure is different.
      // Based on ChatService, getSession returns the session object. 
      // We might need to fetch history if it's not included. 
      // For now, let's assume we start empty or fetch if available.
      // Actually, standard ChatService usually doesn't return messages in listSessions, but getSession might.
      // Let's check if there are messages in the response.
      if (sessionData) {
        // Update session metrics
        if (sessionData.metrics) {
          this.sessionMetrics.set({
            total_tokens: sessionData.metrics.total_tokens || 0,
            total_cost: sessionData.metrics.total_estimated_cost || 0
          });
        } else {
          this.sessionMetrics.set({ total_tokens: 0, total_cost: 0 });
        }

        if (sessionData.messages) {
          const mappedMessages: Message[] = sessionData.messages
            .map((m: any) => ({
              id: m.id,
              role: m.role,
              content: m.content,
              timestamp: new Date(m.timestamp),
              toolCalls: m.toolCalls?.map((tc: any) => {
                // Convert legacy status values to new format
                let status: 'pending' | 'success' | 'error' = 'pending';
                if (tc.status === 'completed' || tc.status === 'success') {
                  status = 'success';
                } else if (tc.status === 'failed' || tc.status === 'error') {
                  status = 'error';
                }

                // Generate missing toolUseId for backward compatibility
                const toolUseId = tc.toolUseId || tc.id || `legacy-${Date.now()}-${Math.random()}`;

                return {
                  toolName: tc.name || tc.toolName || 'unknown',
                  toolUseId: toolUseId,
                  input: typeof tc.input === 'string' ? tc.input : JSON.stringify(tc.input || {}),
                  output: tc.result ? (typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result, null, 2)) : tc.output || '',
                  status: status,
                  error: tc.error
                };
              })
            }))
            .filter((msg: Message) => {
              // Filter out empty messages
              const hasContent = msg.content?.trim();
              const hasToolCalls = msg.toolCalls && msg.toolCalls.length > 0;
              return hasContent || hasToolCalls;
            });
          this.messages.set(mappedMessages);
        }
      }
    });
  }

  deleteSession(sessionId: string, event: Event): void {
    event.stopPropagation(); // Prevent session selection when clicking delete

    // Confirmation dialog
    if (!confirm('Are you sure you want to delete this session? This action cannot be undone.')) {
      return;
    }

    this.chatService.deleteSession(sessionId).subscribe({
      next: (response) => {
        console.log('Session deleted:', response);

        // If the deleted session was active, clear the view
        if (this.activeSessionId() === sessionId) {
          this.activeSessionId.set(null);
          this.messages.set([]);
          this.isDraftMode.set(true);
          this.sessionMetrics.set({ total_tokens: 0, total_cost: 0 });
        }

        // Reload session list
        this.loadSessions();
      },
      error: (error) => {
        console.error('Error deleting session:', error);
        alert('Failed to delete session: ' + (error.error?.message || error.message));
      }
    });
  }

  toggleSidebar() {
    this.sidebarOpen.update(v => !v);
  }

  createNewSession(): void {
    // Clear state and enter draft mode
    // Session will be created when first message is sent
    this.activeSessionId.set(null);
    this.messages.set([]);
    this.isDraftMode.set(true);
    this.sessionMetrics.set({ total_tokens: 0, total_cost: 0 });
  }

  private extractTitleFromMessage(message: string): string {
    let title = message.trim();

    // Remove markdown code blocks
    title = title.replace(/^```[\w]*\s*/, '');
    title = title.replace(/```\s*$/, '');

    // Normalize whitespace
    title = title.replace(/\s+/g, ' ');

    // Truncate at 16 chars (word boundary) - matching backend
    if (title.length > 16) {
      const truncated = title.substring(0, 16).split(' ').slice(0, -1).join(' ');
      title = truncated.length > 8 ? truncated + '...' : title.substring(0, 16) + '...';
    }

    return title || 'New Session';
  }

  private async createSessionWithTitle(sessionId: string, title: string): Promise<void> {
    return new Promise((resolve, reject) => {
      this.chatService.createSession(sessionId, title).subscribe({
        next: (session) => {
          this.waitForSessionReady(session.id).then(() => {
            resolve();
          }).catch((error) => {
            console.error('Session creation failed:', error);
            reject(error);
          });
        },
        error: (error) => {
          console.error('Failed to create session:', error);
          reject(error);
        }
      });
    });
  }

  private waitForSessionReady(sessionId: string, maxAttempts = 10): Promise<void> {
    return new Promise((resolve, reject) => {
      let attempts = 0;

      const checkStatus = () => {
        attempts++;
        this.chatService.getSessionStatus(sessionId).subscribe({
          next: (status) => {
            if (status.ready) {
              resolve();
            } else if (attempts >= maxAttempts) {
              reject(new Error('Session initialization timeout'));
            } else {
              setTimeout(checkStatus, 500);
            }
          },
          error: () => {
            if (attempts >= maxAttempts) {
              reject(new Error('Failed to check session status'));
            } else {
              setTimeout(checkStatus, 500);
            }
          }
        });
      };

      checkStatus();
    });
  }

  private isSessionReady(sessionId: string): Promise<boolean> {
    return new Promise((resolve) => {
      this.chatService.getSessionStatus(sessionId).subscribe({
        next: (status) => resolve(status.ready),
        error: () => resolve(false)
      });
    });
  }

  autoResize(textarea: any) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
  }

  scrollToBottom(): void {
    try {
      this.scrollContainer.nativeElement.scrollTop = this.scrollContainer.nativeElement.scrollHeight;
    } catch (err) { }
  }

  async sendMessage() {
    if (!this.currentInput().trim()) return;

    const userContent = this.currentInput();
    this.currentInput.set(''); // Clear input immediately

    // Reset input height
    if (this.messageInput) {
      this.messageInput.nativeElement.style.height = 'auto';
    }

    // CRITICAL FIX: Add user message to UI immediately
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: userContent,
      timestamp: new Date()
    };
    this.messages.update(msgs => [...msgs, userMsg]);

    try {
      let sessionId = this.activeSessionId();

      // Check if we're in draft mode - create session with message as title
      if (this.isDraftMode()) {
        const newSessionId = crypto.randomUUID();
        const title = this.extractTitleFromMessage(userContent);

        // Create session with meaningful title (async, don't wait)
        this.createSessionWithTitle(newSessionId, title).then(() => {
          console.log('Session created successfully');
        }).catch(err => {
          console.error('Failed to create session:', err);
          // Remove optimistically added session on error
          this.sessions.update(sessions =>
            sessions.filter(s => s.id !== newSessionId)
          );
        });

        // OPTIMISTIC: Update UI immediately (don't wait for server)
        sessionId = newSessionId;
        this.activeSessionId.set(sessionId);
        this.isDraftMode.set(false);

        // OPTIMISTIC: Add session to list immediately
        this.sessions.update(sessions => [{
          id: newSessionId,
          title: title,
          date: new Date(),
          active: true
        }, ...sessions]);
      } else if (!sessionId) {
        // Fallback: No session and not in draft mode (shouldn't normally happen)
        this.createNewSession();
        return; // Exit early, user will need to send again
      }

      // Double-check session is ready
      const isReady = await this.isSessionReady(sessionId);
      if (!isReady) {
        await this.waitForSessionReady(sessionId);
      }

      // Send the actual message
      await this.sendActualMessage(userContent, sessionId);
    } catch (error) {
      console.error('Failed to send message:', error);
      // Show error to user by adding error message
      this.messages.update(msgs => {
        const updated = [...msgs];
        const errorMsg: Message = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `❌ Error: ${error instanceof Error ? error.message : 'Failed to send message'}`,
          timestamp: new Date(),
          isStreaming: false
        };
        return [...updated, errorMsg];
      });
      this.isGenerating.set(false);
    }
  }

  private async sendActualMessage(userContent: string, sessionId: string): Promise<void> {
    // 1. Add User Message (already added in sendMessage)
    this.isGenerating.set(true);

    // Create AbortController for cancellation
    this.currentAbortController = new AbortController();

    // 2. Prepare Assistant Stub
    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      reasoning: '',
      timestamp: new Date(),
      isStreaming: true,
      toolCalls: [],
      chunks: []
    };

    this.messages.update(msgs => [...msgs, assistantMsg]);

    // 3. Stream Response
    try {
      const stream = this.chatService.sendMessageStream(
        sessionId,
        userContent,
        undefined,
        this.currentAbortController.signal
      );
      let startTime = Date.now();
      let tokenCount = 0;

      for await (const event of stream) {
        this.messages.update(msgs => msgs.map(m => {
          if (m.id !== assistantId) return m;

          const updated = { ...m };

          // Handle different event types with raw backend format
          if (event.type === 'data' && event.data?.text) {
            updated.content += event.data.text;
            updated.chunks = [...(updated.chunks || []), event.data.text];
            tokenCount++; // Rough estimation
          } else if (event.type === 'text' && event.content) {
            updated.content += event.content;
            updated.chunks = [...(updated.chunks || []), event.content];
            tokenCount++; // Rough estimation
          } else if (event.type === 'reasoning' && event.data?.text) {
            updated.reasoning = (updated.reasoning || '') + event.data.text;
          } else if (event.type === 'reasoning' && event.reasoning) {
            updated.reasoning = (updated.reasoning || '') + event.reasoning;
          } else if (event.type === 'metrics') {
            // Handle metrics event
            const metricsData = event.data?.metrics || event.metrics;
            if (metricsData) {
              // Update message metrics
              updated.metrics = {
                total_tokens: metricsData.total_tokens || 0,
                input_tokens: metricsData.input_tokens || 0,
                output_tokens: metricsData.output_tokens || 0,
                estimated_cost: metricsData.estimated_cost || metricsData.cost || 0,
                model_id: metricsData.model_id || 'unknown'
              };

              // Update session metrics
              // Note: The backend should ideally return the cumulative session metrics,
              // but if it returns only message metrics, we might need to accumulate them.
              // However, let's assume for now we just want to show the running total if available,
              // or we add this message's cost to the session total.

              // Better approach: If the backend sends the *message* cost, we add it to the session total.
              // But since we might get multiple metrics events (e.g. intermediate), we should be careful not to double count.
              // Usually metrics come at the end.

              // Let's rely on the fact that we loaded the session total at start, 
              // and we add the *incremental* cost of this message when it's done.
              // But wait, if we switch sessions and come back, we reload from backend.
              // So for the live update, we can just add the cost of this message to the *initial* session cost?
              // No, that's complex.

              // Simplest: Just display the message cost for now, or if we want session total,
              // we need to know if this is the *final* metrics event for this message.

              // Let's update the session metrics signal by adding this message's cost to the *current* value
              // BUT only if this is the first time we see metrics for this message?
              // Or better: The session metrics signal holds the *base* session cost (loaded at start) + sum of costs of new messages in this session.

              // Actually, let's just update the UI to show what we have.
              // If we want a live "Session Total", we can update it here.

              const currentSessionMetrics = this.sessionMetrics();
              // This is tricky because metrics might be sent multiple times or we might re-run.
              // Let's just update the signal with a new object that includes this message's contribution.
              // BUT we don't want to keep adding it if we receive multiple metrics events for the same message.

              // For now, let's just log it and maybe update a "current run cost" display?
              // The user asked for "tokens total and cost total for the session".

              // Let's assume the backend *persists* the session total.
              // So if we could fetch the updated session metrics, that would be best.
              // But we don't want to poll.

              // Let's accumulate locally.
              // We need to track which messages we've already accounted for?
              // Or just add the *difference*?

              // Let's try this:
              // We have `this.sessionMetrics` which was loaded from the backend.
              // When we get metrics for a message, we update `this.sessionMetrics` by adding this message's cost/tokens.
              // BUT we must ensure we don't add it twice.
              // Since `sendActualMessage` runs once per message, and `metrics` usually comes once at the end...
              // We can just add it.

              // However, if `metrics` event comes multiple times (e.g. partial), we have a problem.
              // Usually `metrics` comes once at `message_stop`.

              this.sessionMetrics.update(current => ({
                total_tokens: current.total_tokens + (metricsData.total_tokens || 0),
                total_cost: current.total_cost + (metricsData.estimated_cost || metricsData.cost || 0)
              }));
            }
          } else if (event.type === 'tool_use' && event.data) {
            // Handle raw backend format for tool_use events
            if (!updated.toolCalls) {
              updated.toolCalls = [];
            }

            const toolCallData: ToolCall = {
              toolName: event.data.tool_name || event.data.name || 'unknown',
              toolUseId: event.data.tool_use_id || `tool-${Date.now()}-${updated.toolCalls.length}`,
              input: JSON.stringify(event.data.tool_input || event.data.input || {}),
              output: '',
              status: 'pending' // Default status
            };

            // Check if this tool call has a result
            if (event.data.result) {
              toolCallData.output = JSON.stringify(event.data.result, null, 2);
              toolCallData.status = 'success';
            }

            // Add new tool call
            updated.toolCalls = [...updated.toolCalls, toolCallData];
          } else if (event.type === 'tool_use' && event.toolCall) {
            // Ensure toolCalls array exists
            if (!updated.toolCalls) {
              updated.toolCalls = [];
            }

            // Check if this is a new tool call or an update
            // Use index-based matching: find pending tool with same name, or add new
            let toolCallIndex = -1;

            // If event has an explicit index, use it
            if (event.toolCall.index !== undefined) {
              toolCallIndex = event.toolCall.index;
            } else {
              // Otherwise, find existing pending tool by name (for backward compat)
              toolCallIndex = updated.toolCalls.findIndex(
                tc => tc.toolName === event.toolCall.name && tc.status === 'pending'
              );
            }

            const toolCallData: ToolCall = {
              toolName: event.toolCall.name,
              input: JSON.stringify(event.toolCall.input || {}),
              output: '',
              status: 'pending' // Default status
            };

            // Map backend status to frontend status
            if (event.status === 'completed') {
              toolCallData.status = 'success';
            } else if (event.status === 'failed') {
              toolCallData.status = 'error';
            } else if (event.status === 'running') {
              toolCallData.status = 'pending';
            }

            // If tool has result, set output and mark as success (unless already failed)
            if (event.toolCall.result) {
              toolCallData.output = JSON.stringify(event.toolCall.result, null, 2);
              if (!event.status || event.status === 'completed') {
                toolCallData.status = 'success';
              }
            }

            if (toolCallIndex >= 0 && toolCallIndex < updated.toolCalls.length) {
              // Update existing tool call at the found index
              updated.toolCalls[toolCallIndex] = {
                ...updated.toolCalls[toolCallIndex],
                ...toolCallData
              };
            } else {
              // Add new tool call
              updated.toolCalls = [...updated.toolCalls, toolCallData];
            }
          } else if (event.type === 'tool_result') {
            // Handle tool completion results
            const resultData = event.data || event;
            const toolName = resultData.tool_name || resultData.name;
            const toolUseId = resultData.tool_use_id;

            if (!updated.toolCalls) {
              updated.toolCalls = [];
            }

            // Find tool by toolUseId first, then fall back to name+status
            let toolIndex = -1;
            if (toolUseId) {
              toolIndex = updated.toolCalls.findIndex(tc => tc.toolUseId === toolUseId);
            }

            // Fallback to original logic for backward compatibility
            if (toolIndex === -1) {
              toolIndex = updated.toolCalls.findIndex(
                tc => tc.toolName === toolName && tc.status === 'pending'
              );
            }

            if (toolIndex >= 0) {
              // Update the existing tool with result
              updated.toolCalls[toolIndex] = {
                ...updated.toolCalls[toolIndex],
                output: JSON.stringify(
                  resultData.result || resultData,
                  null,
                  2
                ),
                status: 'success'
              };
            } else {
              // Tool not found - might have been missed or out of order
              console.warn(`Tool result received for unknown tool: ${toolName}`);
            }
          } else if (event.type === 'tool_error') {
            // Handle tool errors
            const resultData = event.data || event;
            const toolName = resultData.tool_name || 'unknown';
            const toolUseId = resultData.tool_use_id;

            if (!updated.toolCalls) {
              updated.toolCalls = [];
            }

            // Find tool by toolUseId or name+status
            let toolIndex = -1;
            if (toolUseId) {
              toolIndex = updated.toolCalls.findIndex(tc => tc.toolUseId === toolUseId);
            }

            if (toolIndex === -1) {
              // Create error tool entry if not found
              updated.toolCalls.push({
                toolName: toolName,
                toolUseId: toolUseId || `error-${Date.now()}`,
                input: 'Unknown',
                output: '',
                status: 'error',
                error: resultData.error || 'Tool execution failed'
              });
            } else {
              // Update existing tool with error
              updated.toolCalls[toolIndex] = {
                ...updated.toolCalls[toolIndex],
                status: 'error',
                error: resultData.error || 'Tool execution failed'
              };
            }
          } else if (event.type === 'metrics' && event.data?.metrics) {
            // Handle raw backend format for metrics events
            updated.metrics = {
              total_tokens: event.data.metrics.total_tokens || 0,
              input_tokens: event.data.metrics.input_tokens || 0,
              output_tokens: event.data.metrics.output_tokens || 0,
              estimated_cost: event.data.metrics.estimated_cost || 0,
              model_id: event.data.metrics.model_id || 'unknown'
            };
          } else if (event.type === 'metrics' && event.metrics) {
            // Store metrics for display (fallback for transformed format)
            updated.metrics = {
              total_tokens: event.metrics.total_tokens || 0,
              input_tokens: event.metrics.input_tokens || 0,
              output_tokens: event.metrics.output_tokens || 0,
              estimated_cost: event.metrics.estimated_cost || 0,
              model_id: event.metrics.model_id || 'unknown'
            };
          } else if (event.type === 'error') {
            updated.error = event.error || 'Unknown error occurred';
          } else if (event.type === 'done') {
            // Stream finished
            updated.isStreaming = false;
          }

          return updated;
        }));
      }

      // Calculate metrics
      const endTime = Date.now();
      const duration = endTime - startTime;
      this.metrics.set({
        latency: duration,
        tokensPerSec: tokenCount / (duration / 1000)
      });

    } catch (error: any) {
      console.error('Error sending message:', error);

      // Handle cancellation separately from errors
      if (error.name === 'AbortError') {
        console.log('Stream cancelled by user');
        this.messages.update(msgs => msgs.map(m => {
          if (m.id === assistantId) {
            return {
              ...m,
              content: m.content || '',
              isStreaming: false
            };
          }
          return m;
        }));
      } else {
        this.messages.update(msgs => msgs.map(m =>
          m.id === assistantId ? { ...m, content: m.content + '\n[Error generating response]' } : m
        ));
      }
    } finally {
      this.isGenerating.set(false);
      this.currentAbortController = null;
      this.messages.update(msgs => msgs.map(m =>
        m.id === assistantId ? { ...m, isStreaming: false } : m
      ));
    }
  }

  updateSessionTitle(sessionId: string, newTitle: string): void {
    this.chatService.updateSessionTitle(sessionId, newTitle).subscribe({
      next: (response) => {
        console.log('Session title updated:', response);
        // Update session in the local list
        this.sessions.update(sessions =>
          sessions.map(session =>
            session.id === sessionId
              ? { ...session, title: newTitle }
              : session
          )
        );
      },
      error: (error) => {
        console.error('Error updating session title:', error);
      }
    });
  }

  stopGeneration(): void {
    if (this.currentAbortController) {
      console.log('Stopping generation...');
      this.currentAbortController.abort();
      this.currentAbortController = null;
      this.isGenerating.set(false);
    }
  }
}