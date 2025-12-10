import { Component, signal, ViewChild, ElementRef, AfterViewChecked, ChangeDetectionStrategy, model, OnInit, inject, EffectRef, effect, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService, Session, Message as ServiceMessage, ToolCall as ServiceToolCall } from './services/chat.service';
import { MarkdownPipe } from './pipes/markdown.pipe';
import { DesktopService, GodotStatus } from './services/desktop.service';
import { DocumentationService, DocumentationStatus, RebuildProgress } from './services/documentation.service';
import { AuthService, Transaction } from './services/auth.service';
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
  imports: [CommonModule, FormsModule, MarkdownPipe],
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
              class="relative w-full text-left px-4 py-2 text-sm hover:bg-[#2d3546] transition-colors border-l-2 flex justify-between items-center group cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#478cbf]/50"
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
              <span>{{ sessionMetrics().total_tokens | number:'1.0-0' }} tok</span>
            </div>
          </div>
          
          <!-- User Account / Balance -->
          <div class="flex items-center gap-2">
            @if (authService.isAuthenticated()) {
              <!-- Balance Display -->
              <button 
                (click)="openCreditsPage()"
                class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium bg-[#1a1e29] border border-[#2d3546] hover:border-green-500/50 transition-colors"
                title="Credits - Click to add more"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 text-green-400">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M21 12a2.25 2.25 0 00-2.25-2.25H15a3 3 0 11-6 0H5.25A2.25 2.25 0 003 12m18 0v6a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 18v-6m18 0V9M3 12V9m18 0a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 9m18 0V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v3" />
                </svg>
                <span class="text-green-400"><span>$</span>{{ (authService.creditBalance() ?? 0) | number: '1.2-2' }}</span>
              </button>
              <!-- User Menu Button -->
              <button 
                (click)="openAccountMenu()"
                class="flex items-center gap-1.5 px-2 py-1.5 rounded-md text-xs bg-[#1a1e29] border border-[#2d3546] hover:border-[#478cbf]/50 transition-colors"
                title="Account"
              >
                <div class="w-5 h-5 rounded-full bg-gradient-to-tr from-[#478cbf] to-cyan-400 flex items-center justify-center text-[10px] font-bold text-white">
                  {{ authService.currentUser()?.email?.charAt(0)?.toUpperCase() || 'U' }}
                </div>
              </button>
            } @else {
              <!-- Login Button -->
              <button 
                (click)="openAuthModal()"
                class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-[#478cbf] text-white hover:bg-[#367fa9] transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
                </svg>
                Sign In
              </button>
            }
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
                            <details class="my-2 border border-[#3b4458] rounded-md bg-[#161922] overflow-hidden font-mono text-xs shadow-sm group/tool" [open]="tool.status === 'pending'">
                                <summary class="bg-[#1f2430] px-3 py-2 flex items-center justify-between border-b border-[#2d3546] cursor-pointer select-none hover:bg-[#252b3a] transition-colors list-none">
                                    <div class="flex items-center gap-2 text-gray-300">
                                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 text-[#478cbf]">
                                            <path stroke-linecap="round" stroke-linejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 18" />
                                        </svg>
                                        <span>{{ tool.toolName }}</span>
                                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-3 h-3 text-gray-500 transition-transform group-open/tool:rotate-90">
                                            <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                                        </svg>
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
                                </summary>
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
                            </details>
                        }
                    }

                    <!-- Main Content -->
                    <div class="prose prose-invert prose-sm max-w-none text-gray-300 leading-relaxed break-words [&>*:last-child]:mb-0">
                      @if (msg.isStreaming && msg.chunks) {
                         @for (chunk of msg.chunks; track $index) {
                           <span class="relative animate-fade-in-up whitespace-pre-wrap">{{ chunk }}</span>
                         }
                         @if (!msg.reasoning) {
                            <span class="inline-block w-1.5 h-4 bg-[#478cbf] align-middle ml-0.5 animate-pulse"></span>
                         }
                      } @else {
                         <div [innerHTML]="msg.content | markdown"></div>
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
            <!-- Plan Review Card (shown when plan is pending or regenerating) -->
            @if (hasPendingPlan()) {
              <div class="max-w-3xl mx-auto mb-4 bg-[#262c3b] rounded-xl border border-[#478cbf]/30 overflow-hidden">
                <!-- Header -->
                <div class="flex items-center justify-between px-4 py-3 bg-[#1e2330] border-b border-[#2d3546]">
                  <div class="flex items-center gap-2 text-sm">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5 text-yellow-400">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25zM6.75 12h.008v.008H6.75V12zm0 3h.008v.008H6.75V15zm0 3h.008v.008H6.75V18z" />
                    </svg>
                    @if (isGenerating() && !pendingPlanContent()) {
                      <span class="font-medium text-gray-200">Generating Plan...</span>
                      <span class="w-4 h-4 border-2 border-yellow-400/30 border-t-yellow-400 rounded-full animate-spin"></span>
                    } @else if (isGenerating()) {
                      <span class="font-medium text-gray-200">Plan (Updating...)</span>
                      <span class="w-2 h-2 rounded-full bg-yellow-400 animate-pulse"></span>
                    } @else {
                      <span class="font-medium text-gray-200">Plan Generated</span>
                      <span class="w-2 h-2 rounded-full bg-yellow-400 animate-pulse"></span>
                    }
                  </div>
                </div>

                <!-- Plan Content -->
                <div class="px-4 py-3 max-h-80 overflow-y-auto">
                  @if (!pendingPlanContent() && isGenerating()) {
                    <!-- Loading state -->
                    <div class="flex items-center justify-center py-8">
                      <div class="flex flex-col items-center gap-3">
                        <div class="w-8 h-8 border-3 border-[#478cbf]/30 border-t-[#478cbf] rounded-full animate-spin"></div>
                        <span class="text-sm text-gray-400">Agent is thinking...</span>
                      </div>
                    </div>
                  } @else if (pendingPlanContent()) {
                    <div class="prose prose-invert prose-sm max-w-none text-gray-300 leading-relaxed whitespace-pre-wrap">{{ stripPlanFences(pendingPlanContent()) }}@if (isGenerating()) {<span class="inline-block w-1.5 h-4 bg-[#478cbf] align-middle ml-0.5 animate-pulse"></span>}</div>
                  } @else {
                    <div class="text-gray-500 text-sm">No plan content available.</div>
                  }
                </div>

                <!-- Feedback Input (shown when requesting changes) -->
                @if (showFeedbackInput()) {
                  <div class="px-4 py-3 border-t border-[#2d3546] bg-[#1e2330]">
                    <label class="block text-xs text-gray-400 mb-2">What changes would you like?</label>
                    <textarea
                      [(ngModel)]="planFeedback"
                      placeholder="Describe the changes you want..."
                      class="w-full bg-[#161922] border border-[#2d3546] rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-[#478cbf] resize-none"
                      rows="3"
                    ></textarea>
                  </div>
                }

                <!-- Action Buttons (only show when not generating) -->
                @if (!isGenerating()) {
                <div class="flex items-center justify-end gap-2 px-4 py-3 border-t border-[#2d3546] bg-[#1e2330]">
                  @if (showFeedbackInput()) {
                    <button
                      (click)="cancelFeedback()"
                      class="px-4 py-2 rounded-lg text-sm font-medium text-gray-400 hover:text-white hover:bg-[#2d3546] transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      (click)="submitFeedback()"
                      [disabled]="!planFeedback()"
                      class="px-4 py-2 rounded-lg text-sm font-medium bg-[#478cbf] text-white hover:bg-[#367fa9] disabled:opacity-50 transition-colors"
                    >
                      Regenerate Plan
                    </button>
                  } @else {
                    <button
                      (click)="requestChanges()"
                      class="px-4 py-2 rounded-lg text-sm font-medium text-gray-400 hover:text-white hover:bg-[#2d3546] transition-colors"
                    >
                      Request Changes
                    </button>
                    <button
                      (click)="approvePlan()"
                      [disabled]="isApproving()"
                      class="px-4 py-2 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 transition-colors flex items-center gap-2"
                    >
                      @if (isApproving()) {
                        <span class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                        Executing...
                      } @else {
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4">
                          <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                        Accept & Execute
                      }
                    </button>
                  }
                </div>
                }
              </div>
            }

            <div class="max-w-3xl mx-auto bg-[#2d3546] rounded-xl shadow-lg border border-[#3b4458] focus-within:border-[#478cbf] focus-within:ring-1 focus-within:ring-[#478cbf]/50 transition-all duration-200 overflow-hidden">
              <!-- Textarea -->
              <textarea
                #messageInput
                [(ngModel)]="currentInput"
                (keydown.enter)="$event.preventDefault(); sendMessage()"
                placeholder="Ask Godoty a question..."
                class="w-full bg-transparent text-gray-200 placeholder-gray-500 text-sm px-4 py-3 focus:outline-none resize-none max-h-48 overflow-y-auto"
                rows="1"
                (input)="autoResize($event.target)"
              ></textarea>

              <!-- Bottom Action Bar -->
              <div class="flex items-center justify-between px-3 py-2 border-t border-[#3b4458]/50">
                <!-- Left: Mode Toggle -->
                <button
                  (click)="toggleMode()"
                  class="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-all hover:bg-[#3b4458]/50"
                  [class.text-blue-400]="currentMode() === 'learning'"
                  [class.text-yellow-400]="currentMode() === 'planning'"
                  [class.text-green-400]="currentMode() === 'execution'"
                  [title]="currentMode() === 'learning' ? 'Learning Mode: Agent will research and gather information with web search' : currentMode() === 'planning' ? 'Planning Mode: Agent will propose a plan for approval' : 'Execution Mode: Agent will directly execute actions'"
                >
                  @if (currentMode() === 'learning') {
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-3.5 h-3.5">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
                    </svg>
                    <span>Learning</span>
                  } @else if (currentMode() === 'planning') {
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-3.5 h-3.5">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 6.75h12M8.25 12h12m-12 5.25h12M3.75 6.75h.007v.008H3.75V6.75zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zM3.75 12h.007v.008H3.75V12zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm-.375 5.25h.007v.008H3.75v-.008zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
                    </svg>
                    <span>Planning</span>
                  } @else {
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-3.5 h-3.5">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                    </svg>
                    <span>Execution</span>
                  }
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-3 h-3 opacity-50">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M8.25 15L12 18.75 15.75 15m-7.5-6L12 5.25 15.75 9" />
                  </svg>
                </button>

                <!-- Right: Send/Stop Button -->
                @if (isGenerating()) {
                  <button
                    (click)="stopGeneration()"
                    class="flex items-center justify-center w-8 h-8 rounded-full bg-red-500 text-white hover:bg-red-600 transition-all"
                    title="Stop generation"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
                      <path d="M5.25 3A2.25 2.25 0 003 5.25v9.5A2.25 2.25 0 005.25 17h9.5A2.25 2.25 0 0017 14.75v-9.5A2.25 2.25 0 0014.75 3h-9.5z" />
                    </svg>
                  </button>
                } @else {
                  <button
                    (click)="sendMessage()"
                    [disabled]="!currentInput()"
                    class="flex items-center justify-center w-8 h-8 rounded-full bg-[#478cbf] text-white hover:bg-[#367fa9] disabled:opacity-30 disabled:bg-[#3b4458] disabled:text-gray-500 transition-all"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
                      <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A2 2 0 005.635 9.75h5.736a.75.75 0 010 1.5H5.636a2 2 0 00-1.942 1.586l-1.414 4.925a.75.75 0 00.826.95 28.89 28.89 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
                    </svg>
                  </button>
                }
              </div>
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

              <!-- Documentation Status Capsule -->
              <div class="bg-[#161922] border border-[#2d3546] rounded-lg px-3 py-2">
                @if (documentationStatus(); as status) {
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex items-center gap-2 min-w-0">
                      <!-- Status Icon -->
                      @switch (status?.status) {
                        @case ('not_built') {
                          <span class="text-gray-400 text-sm">📚</span>
                        }
                        @case ('building') {
                          <span class="text-yellow-400 text-sm">🔄</span>
                        }
                        @case ('completed') {
                          <span class="text-green-400 text-sm">✅</span>
                        }
                        @case ('error') {
                          <span class="text-red-400 text-sm">❌</span>
                        }
                      }
                      <!-- Version -->
                      <span class="text-xs font-medium" [class.text-[#478cbf]]="status.godot_version" [class.text-gray-500]="!status.godot_version">
                        {{ status.godot_version || 'Not built' }}
                      </span>
                      <!-- Build Date (if available) -->
                      @if (status?.build_timestamp && status?.status === 'completed') {
                        <span class="text-[10px] text-gray-500 hidden sm:inline">• {{formatDate(status.build_timestamp!)}}</span>
                      }
                    </div>
                    <!-- Size -->
                    @if (status?.size_mb) {
                      <span class="text-[10px] text-gray-500 flex-shrink-0">{{status.size_mb}} MB</span>
                    }
                  </div>
                  @if (status?.error_message) {
                    <p class="text-[10px] text-red-400 mt-1 truncate">{{status.error_message}}</p>
                  }
                } @else {
                  <span class="text-xs text-gray-500">Loading...</span>
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

            <!-- Project Index Section -->
            <div class="space-y-2">
              <label class="block text-xs font-medium text-gray-400 uppercase tracking-wider">Project Context Index</label>

              <!-- Index Status Capsule -->
              <div class="bg-[#161922] border border-[#2d3546] rounded-lg px-3 py-2">
                @if (godotStatus()?.index_status; as indexStatus) {
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex items-center gap-2 min-w-0">
                      <!-- Status Icon -->
                      @switch (indexStatus.status) {
                        @case ('not_started') {
                          <span class="text-gray-400 text-sm">📂</span>
                        }
                        @case ('scanning') {
                          <span class="text-yellow-400 text-sm animate-pulse">🔍</span>
                        }
                        @case ('building_graph') {
                          <span class="text-yellow-400 text-sm animate-pulse">🔗</span>
                        }
                        @case ('building_vectors') {
                          <span class="text-yellow-400 text-sm animate-pulse">🧠</span>
                        }
                        @case ('complete') {
                          <span class="text-green-400 text-sm">✅</span>
                        }
                        @case ('failed') {
                          <span class="text-red-400 text-sm">❌</span>
                        }
                      }
                      <!-- Phase Text -->
                      <span class="text-xs font-medium" 
                        [class.text-[#478cbf]]="indexStatus.status === 'complete'"
                        [class.text-yellow-400]="indexStatus.status === 'scanning' || indexStatus.status === 'building_graph' || indexStatus.status === 'building_vectors'"
                        [class.text-red-400]="indexStatus.status === 'failed'"
                        [class.text-gray-500]="indexStatus.status === 'not_started'">
                        {{ indexStatus.phase || (indexStatus.status === 'complete' ? 'Indexed' : 'Not indexed') }}
                      </span>
                    </div>
                    <!-- Progress Percent (when indexing) -->
                    @if (indexStatus.progress_percent > 0 && indexStatus.status !== 'complete' && indexStatus.status !== 'failed') {
                      <span class="text-[10px] text-gray-500 flex-shrink-0">{{indexStatus.progress_percent}}%</span>
                    }
                  </div>

                  <!-- Progress Bar (when actively indexing) -->
                  @if (indexStatus.status !== 'not_started' && indexStatus.status !== 'complete' && indexStatus.status !== 'failed') {
                    <div class="mt-2">
                      <div class="w-full bg-gray-700 rounded-full h-1.5">
                        <div
                          class="bg-[#478cbf] h-1.5 rounded-full transition-all duration-300"
                          [style.width.%]="indexStatus.progress_percent"
                        ></div>
                      </div>
                      @if (indexStatus.current_file) {
                        <div class="text-[10px] text-gray-500 mt-1 truncate">{{indexStatus.current_file}}</div>
                      }
                    </div>
                  }

                  <!-- Error Message -->
                  @if (indexStatus.error) {
                    <p class="text-[10px] text-red-400 mt-1 truncate">{{indexStatus.error}}</p>
                  }
                } @else if (isGodotConnected()) {
                  <span class="text-xs text-gray-500">Waiting for index status...</span>
                } @else {
                  <span class="text-xs text-gray-500">Connect to Godot to index project</span>
                }
              </div>

              <p class="text-[10px] text-gray-500">The project is automatically indexed when you connect to Godot. This enables context-aware AI assistance.</p>
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
    
    <!-- Auth Modal (Login/Signup/OTP) -->
    @if (authModalOpen()) {
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" (click)="closeAuthModal()">
        <div class="bg-[#1a1e29] border border-[#2d3546] rounded-xl shadow-2xl w-full max-w-sm overflow-hidden" (click)="$event.stopPropagation()">
          <!-- Header -->
          <div class="px-6 py-4 border-b border-[#2d3546] flex justify-between items-center bg-[#202531]">
            <h3 class="text-lg font-semibold text-gray-200">
              @if (authModalMode() === 'otp') {
                Enter Verification Code
              } @else {
                {{ authModalMode() === 'login' ? 'Sign In' : 'Create Account' }}
              }
            </h3>
            <button (click)="closeAuthModal()" class="text-gray-500 hover:text-white transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          
          <!-- OTP Verification Form -->
          @if (authModalMode() === 'otp') {
            <div class="p-6 space-y-4">
              @if (authError()) {
                <div class="bg-red-900/30 border border-red-500/50 rounded-lg px-4 py-2 text-sm text-red-300">
                  {{ authError() }}
                </div>
              }
              
              <div class="text-center space-y-2">
                <div class="w-12 h-12 mx-auto bg-[#478cbf]/10 rounded-full flex items-center justify-center">
                  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-6 h-6 text-[#478cbf]">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                  </svg>
                </div>
                <p class="text-sm text-gray-400">
                  We sent a verification code to<br/>
                  <span class="text-gray-200 font-medium">{{ magicLinkEmail() }}</span>
                </p>
              </div>
              
              <div class="space-y-2">
                <label class="block text-xs font-medium text-gray-400 uppercase tracking-wider">Verification Code</label>
                <input 
                  type="text" 
                  [(ngModel)]="authForm.otpToken" 
                  placeholder="Enter 6-digit code"
                  (keydown.enter)="verifyOTP()"
                  class="w-full bg-[#161922] border border-[#2d3546] rounded-lg px-4 py-2.5 text-sm text-gray-200 text-center tracking-widest font-mono focus:outline-none focus:border-[#478cbf] focus:ring-1 focus:ring-[#478cbf] transition-all placeholder-gray-600"
                  maxlength="6"
                >
              </div>
            </div>
            
            <div class="px-6 py-4 border-t border-[#2d3546] bg-[#202531] space-y-3">
              <button 
                (click)="verifyOTP()" 
                [disabled]="authService.isLoading() || !authForm.otpToken"
                class="w-full px-4 py-2.5 rounded-lg text-sm font-medium bg-[#478cbf] text-white hover:bg-[#367fa9] disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                @if (authService.isLoading()) {
                  <span class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                }
                Verify Code
              </button>
              
              <div class="flex items-center justify-between text-sm">
                <button (click)="backToLogin()" class="text-gray-400 hover:text-white transition-colors">
                  ← Back to login
                </button>
                <button 
                  (click)="sendMagicLink()"
                  [disabled]="authService.isLoading()"
                  class="text-[#478cbf] hover:underline disabled:opacity-50"
                >
                  Resend code
                </button>
              </div>
            </div>
          } @else {
            <!-- Login/Signup Form -->
            <div class="p-6 space-y-4">
              @if (authError()) {
                <div class="bg-red-900/30 border border-red-500/50 rounded-lg px-4 py-2 text-sm text-red-300">
                  {{ authError() }}
                </div>
              }
              
              <div class="space-y-2">
                <label class="block text-xs font-medium text-gray-400 uppercase tracking-wider">Email</label>
                <input 
                  type="email" 
                  [(ngModel)]="authForm.email" 
                  placeholder="you@example.com" 
                  class="w-full bg-[#161922] border border-[#2d3546] rounded-lg px-4 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-[#478cbf] focus:ring-1 focus:ring-[#478cbf] transition-all placeholder-gray-600"
                >
              </div>
              
              <div class="space-y-2">
                <label class="block text-xs font-medium text-gray-400 uppercase tracking-wider">Password</label>
                <input 
                  type="password" 
                  [(ngModel)]="authForm.password" 
                  placeholder="••••••••"
                  (keydown.enter)="submitAuth()"
                  class="w-full bg-[#161922] border border-[#2d3546] rounded-lg px-4 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-[#478cbf] focus:ring-1 focus:ring-[#478cbf] transition-all placeholder-gray-600"
                >
              </div>
            </div>
            
            <!-- Footer -->
            <div class="px-6 py-4 border-t border-[#2d3546] bg-[#202531] space-y-3">
              <button 
                (click)="submitAuth()" 
                [disabled]="authService.isLoading() || !authForm.email || !authForm.password"
                class="w-full px-4 py-2.5 rounded-lg text-sm font-medium bg-[#478cbf] text-white hover:bg-[#367fa9] disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                @if (authService.isLoading()) {
                  <span class="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                }
                {{ authModalMode() === 'login' ? 'Sign In' : 'Create Account' }}
              </button>
              
              <!-- Magic Link Option -->
              @if (authModalMode() === 'login') {
                <button 
                  (click)="sendMagicLink()"
                  [disabled]="authService.isLoading() || !authForm.email"
                  class="w-full px-4 py-2 rounded-lg text-sm font-medium text-gray-300 border border-[#2d3546] hover:border-[#478cbf]/50 hover:bg-[#2d3546]/50 disabled:opacity-50 transition-colors"
                >
                  Send Magic Link Instead
                </button>
              }
              
              <!-- Divider -->
              <div class="flex items-center gap-3 py-1">
                <div class="flex-1 h-px bg-[#2d3546]"></div>
                <span class="text-xs text-gray-500 uppercase">or continue with</span>
                <div class="flex-1 h-px bg-[#2d3546]"></div>
              </div>
              
              <!-- OAuth Buttons -->
              <div class="flex gap-2">
                <button 
                  (click)="signInWithOAuth('google')"
                  [disabled]="authService.isLoading()"
                  class="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-gray-300 bg-[#161922] border border-[#2d3546] hover:border-[#478cbf]/50 hover:bg-[#2d3546]/50 disabled:opacity-50 transition-colors"
                >
                  <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                  </svg>
                  Google
                </button>
                
                <button 
                  (click)="signInWithOAuth('github')"
                  [disabled]="authService.isLoading()"
                  class="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-gray-300 bg-[#161922] border border-[#2d3546] hover:border-[#478cbf]/50 hover:bg-[#2d3546]/50 disabled:opacity-50 transition-colors"
                >
                  <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
                  </svg>
                  GitHub
                </button>
              </div>
              
              <div class="text-center text-sm text-gray-400">
                @if (authModalMode() === 'login') {
                  Don't have an account? 
                  <button (click)="switchAuthMode()" class="text-[#478cbf] hover:underline">Sign up</button>
                } @else {
                  Already have an account?
                  <button (click)="switchAuthMode()" class="text-[#478cbf] hover:underline">Sign in</button>
                }
              </div>
            </div>
          }
        </div>
      </div>
    }
    
    <!-- Insufficient Credits Modal -->
    @if (insufficientCreditsOpen()) {
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
        <div class="bg-[#1a1e29] border border-red-500/30 rounded-xl shadow-2xl w-full max-w-sm overflow-hidden">
          <div class="p-6 text-center space-y-4">
            <div class="w-16 h-16 mx-auto bg-red-500/10 rounded-full flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-8 h-8 text-red-400">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
              </svg>
            </div>
            <h3 class="text-lg font-semibold text-gray-200">Insufficient Credits</h3>
            <p class="text-sm text-gray-400">Your credit balance is too low to continue. Please add more credits to keep using Godoty.</p>
            <div class="flex gap-3 pt-2">
              <button 
                (click)="closeInsufficientCreditsModal()"
                class="flex-1 px-4 py-2 rounded-lg text-sm font-medium text-gray-400 hover:text-white hover:bg-[#2d3546] transition-colors"
              >
                Later
              </button>
              <button 
                (click)="closeInsufficientCreditsModal(); openCreditsPage()"
                class="flex-1 px-4 py-2 rounded-lg text-sm font-medium bg-green-600 text-white hover:bg-green-700 transition-colors"
              >
                Add Credits
              </button>
            </div>
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
  authService = inject(AuthService);

  sidebarOpen = signal(true);
  currentInput = signal('');
  isGenerating = signal(false);
  private currentAbortController: AbortController | null = null;
  activeSessionId = signal<string | null>(null);
  isDraftMode = signal(false);

  // Settings State
  settingsOpen = signal(false);
  settingsForm = { model_id: '' };

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

  // Planning Mode State
  hasPendingPlan = signal(false);
  isApproving = signal(false);
  currentMode = signal<'learning' | 'planning' | 'execution'>('planning');
  pendingPlanContent = signal<string | null>(null);
  showFeedbackInput = signal(false);
  planFeedback = signal('');

  // Auth Modal State
  authModalOpen = signal(false);
  authModalMode = signal<'login' | 'signup' | 'otp'>('login');
  authForm = { email: '', password: '', otpToken: '' };
  authError = signal<string | null>(null);
  magicLinkEmail = signal<string | null>(null);  // Store email for OTP verification

  // Account Menu State
  accountMenuOpen = signal(false);

  // Insufficient Credits Modal
  insufficientCreditsOpen = signal(false);

  constructor() {
    // Effect to scroll to bottom when messages change DURING generation
    effect(() => {
      this.messages();
      // Only auto-scroll if actively generating a response
      if (this.isGenerating()) {
        setTimeout(() => this.scrollToBottom(), 0);
      }
    });
  }

  @HostListener('click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    const target = event.target as HTMLElement;
    const copyBtn = target.closest('.copy-btn');

    if (copyBtn) {
      const group = copyBtn.closest('.group');
      const codeBlock = group?.querySelector('code');
      if (codeBlock && codeBlock.textContent) {
        navigator.clipboard.writeText(codeBlock.textContent).then(() => {
          // Visual feedback
          const originalContent = copyBtn.innerHTML;
          copyBtn.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="#4ade80" class="w-3.5 h-3.5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
            </svg>
            <span class="text-green-400">Copied!</span>
          `;
          setTimeout(() => {
            copyBtn.innerHTML = originalContent;
          }, 2000);
        }).catch(err => console.error('Failed to copy functionality:', err));
      }
    }
  }

  ngOnInit() {
    // Check for auth callback code (PKCE)
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');

    if (code) {
      // Clean URL immediately
      window.history.replaceState({}, document.title, window.location.pathname);

      // Exchange code for session
      this.authService.exchangeCode(code).subscribe({
        next: (result) => {
          if (result.success) {
            console.log('Successfully authenticated via OAuth code');
          } else {
            console.error('OAuth code exchange failed:', result.error);
          }
        },
        error: (err) => console.error('OAuth exchange error:', err)
      });
    }
    // Start in draft mode optimistically
    this.isDraftMode.set(true);

    this.loadSessions();

    // Subscribe to Godot Status (includes chat readiness)
    this.desktopService.streamGodotStatus().subscribe(status => {
      this.godotStatus.set(status);
      this.isGodotConnected.set(status.state === 'connected');

      // If we have a project path, tell chat service
      if (status.project_path) {
        this.chatService.setProjectPath(status.project_path);
      }

      // Update chat readiness from SSE stream (no polling needed!)
      if (status.chat_ready) {
        this.chatReady.set(status.chat_ready.ready);
        this.chatDisabledMessage.set(status.chat_ready.ready ? '' : status.chat_ready.message);
      }
    });

    // Subscribe to Project Metrics
    this.chatService.projectMetrics$.subscribe(metrics => {
      // Update global metrics if needed, or just use per-message metrics
    });

    // Only do initial chat readiness check for fallback
    // (SSE will provide updates, no polling needed)
    this.checkChatReadiness();
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
            model_id: config.model_id || ''
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

  /**
   * Strip markdown code block fences from plan content
   * Removes ```plan, ```markdown, or generic ``` fences
   */
  stripPlanFences(content: string | null): string {
    if (!content) return '';
    let stripped = content.trim();

    // Remove opening fence (```plan, ```markdown, or just ```)
    const openFenceRegex = /^```(?:plan|markdown)?\s*\n?/;
    stripped = stripped.replace(openFenceRegex, '');

    // Remove closing fence
    const closeFenceRegex = /\n?```\s*$/;
    stripped = stripped.replace(closeFenceRegex, '');

    return stripped.trim();
  }


  selectSession(sessionId: string) {
    this.activeSessionId.set(sessionId);
    this.messages.set([]); // Clear current messages
    this.isDraftMode.set(false); // Exit draft mode when selecting a session

    // Clear any previous plan state
    this.hasPendingPlan.set(false);
    this.pendingPlanContent.set(null);
    this.showFeedbackInput.set(false);
    this.planFeedback.set('');

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

    // Check for pending plan in this session
    this.chatService.getPlanStatus(sessionId).subscribe({
      next: (planStatus) => {
        if (planStatus.has_pending_plan && planStatus.plan) {
          this.hasPendingPlan.set(true);
          this.pendingPlanContent.set(planStatus.plan);
          console.log('Restored pending plan for session');
        }
      },
      error: (err) => console.log('No plan status available:', err)
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

          // Clear any previous plan state
          this.hasPendingPlan.set(false);
          this.pendingPlanContent.set(null);
          this.showFeedbackInput.set(false);
          this.planFeedback.set('');
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

    // Clear any previous plan state
    this.hasPendingPlan.set(false);
    this.pendingPlanContent.set(null);
    this.showFeedbackInput.set(false);
    this.planFeedback.set('');
  }


  private extractTitleFromMessage(message: string): string {
    let title = message.trim();

    // Remove markdown code blocks
    title = title.replace(/^```[\w]*\s*/, '');
    title = title.replace(/```\s*$/, '');

    // Normalize whitespace
    title = title.replace(/\s+/g, ' ');

    // Truncate at 60 chars (was 16)
    if (title.length > 60) {
      const truncated = title.substring(0, 60).split(' ').slice(0, -1).join(' ');
      title = truncated.length > 20 ? truncated + '...' : title.substring(0, 60) + '...';
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
        this.currentMode(),
        this.currentAbortController.signal
      );
      let startTime = Date.now();
      let tokenCount = 0;
      let accumulatedContent = '';  // Track content outside the map for plan capture

      for await (const event of stream) {
        this.messages.update(msgs => msgs.map(m => {
          if (m.id !== assistantId) return m;

          const updated = { ...m };

          // Handle different event types with raw backend format
          if (event.type === 'data' && event.data?.text) {
            updated.content += event.data.text;
            updated.chunks = [...(updated.chunks || []), event.data.text];
            accumulatedContent += event.data.text;
            tokenCount++; // Rough estimation
          } else if (event.type === 'text' && event.data?.content) {
            // Backend sends {type: 'text', data: {content: ...}}
            updated.content += event.data.content;
            updated.chunks = [...(updated.chunks || []), event.data.content];
            accumulatedContent += event.data.content;
            tokenCount++;
          } else if (event.type === 'text' && event.content) {
            updated.content += event.content;
            updated.chunks = [...(updated.chunks || []), event.content];
            accumulatedContent += event.content;
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
              // Match by name, prioritizing pending tools
              const pendingIndex = updated.toolCalls.findIndex(
                tc => tc.toolName === toolName && tc.status === 'pending'
              );
              if (pendingIndex >= 0) {
                toolIndex = pendingIndex;
              } else {
                // Last resort: find any matching tool name without output
                toolIndex = updated.toolCalls.findIndex(
                  tc => tc.toolName === toolName && !tc.output
                );
              }
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
                status: resultData.status || 'success'
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

            // Debug: Log the done event
            console.log('[PLAN DEBUG] Done event received:', event);
            console.log('[PLAN DEBUG] accumulatedContent length:', accumulatedContent.length);

            // Check if there's a pending plan from planning mode
            const doneData = event.data || event;
            console.log('[PLAN DEBUG] doneData:', doneData);

            if (doneData.has_pending_plan !== undefined) {
              console.log('[PLAN DEBUG] has_pending_plan:', doneData.has_pending_plan);
              this.hasPendingPlan.set(doneData.has_pending_plan);
              if (doneData.has_pending_plan && accumulatedContent) {
                // Capture the plan content from accumulated text
                this.pendingPlanContent.set(accumulatedContent);
                console.log('[PLAN DEBUG] Plan captured! Length:', accumulatedContent.length);
              }
              if (doneData.mode) {
                this.currentMode.set(doneData.mode as 'planning' | 'execution');
              }
            } else {
              console.log('[PLAN DEBUG] has_pending_plan is undefined in doneData');
            }

            // Mark any remaining pending tools as completed
            // This ensures tools don't stay in 'pending' state if tool_result wasn't received
            if (updated.toolCalls && updated.toolCalls.length > 0) {
              updated.toolCalls = updated.toolCalls.map(tc => ({
                ...tc,
                status: tc.status === 'pending' ? 'success' : tc.status
              }));
            }
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
      } else if (error.message?.includes('401')) {
        // Authentication required
        this.messages.update(msgs => msgs.map(m =>
          m.id === assistantId ? { ...m, content: m.content + '\n[Authentication required. Please log in to continue.]', isStreaming: false } : m
        ));
        this.openAuthModal();
      } else if (error.message?.includes('402')) {
        // Insufficient credits
        this.messages.update(msgs => msgs.map(m =>
          m.id === assistantId ? { ...m, content: m.content + '\n[Insufficient credits. Please add credits to continue.]', isStreaming: false } : m
        ));
        this.handleInsufficientCredits();
      } else {
        this.messages.update(msgs => msgs.map(m =>
          m.id === assistantId ? { ...m, content: m.content + '\n[Error generating response]' } : m
        ));
      }
    } finally {
      this.isGenerating.set(false);
      this.currentAbortController = null;
      this.messages.update(msgs => msgs.map(m =>
        m.id === assistantId ? { ...m, content: m.content.trimEnd(), isStreaming: false } : m
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

  // Plan Management Methods
  async approvePlan(): Promise<void> {
    const sessionId = this.activeSessionId();
    if (!sessionId) return;

    this.isApproving.set(true);
    this.isGenerating.set(true);
    this.currentAbortController = new AbortController();

    // Create assistant message for execution
    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '**🚀 Executing approved plan...**\n\n',
      timestamp: new Date(),
      isStreaming: true,
      toolCalls: []
    };
    this.messages.update(msgs => [...msgs, assistantMsg]);

    try {
      const stream = this.chatService.approvePlanStream(
        sessionId,
        undefined,
        this.currentAbortController.signal
      );

      for await (const event of stream) {
        this.messages.update(msgs => msgs.map(m => {
          if (m.id !== assistantId) return m;
          const updated = { ...m };

          // Handle text events (multiple formats)
          if (event.type === 'data' && event.data?.text) {
            updated.content += event.data.text;
          } else if (event.type === 'text' && event.data?.content) {
            updated.content += event.data.content;
          } else if (event.type === 'text' && event.data?.text) {
            updated.content += event.data.text;
          } else if (event.type === 'tool_use') {
            // Handle tool use
            const toolData = event.data || {};
            const newToolCall = {
              toolName: toolData.tool_name || 'unknown',
              toolUseId: toolData.tool_use_id || `tool-${Date.now()}`,
              input: typeof toolData.tool_input === 'string'
                ? toolData.tool_input
                : JSON.stringify(toolData.tool_input || {}, null, 2),
              output: '',
              status: 'pending' as const,
            };
            updated.toolCalls = [...(updated.toolCalls || []), newToolCall];
          } else if (event.type === 'tool_result') {
            // Handle tool result
            const resultData = event.data || {};
            const toolUseId = resultData.tool_use_id;
            if (toolUseId && updated.toolCalls) {
              updated.toolCalls = updated.toolCalls.map(tc => {
                if (tc.toolUseId === toolUseId) {
                  let output = '';
                  if (typeof resultData.result === 'string') {
                    output = resultData.result;
                  } else if (Array.isArray(resultData.result)) {
                    output = resultData.result.map((r: any) =>
                      typeof r === 'string' ? r : (r.text || JSON.stringify(r))
                    ).join('\n');
                  } else if (resultData.result) {
                    output = JSON.stringify(resultData.result, null, 2);
                  }
                  return { ...tc, output, status: 'success' as const };
                }
                return tc;
              });
            }
          } else if (event.type === 'done') {
            updated.isStreaming = false;
            this.hasPendingPlan.set(false);
            this.pendingPlanContent.set(null);
            this.currentMode.set('planning');
          }

          return updated;
        }));
      }
    } catch (error) {
      console.error('Error executing plan:', error);
      this.messages.update(msgs => msgs.map(m =>
        m.id === assistantId
          ? { ...m, content: m.content + '\n\n❌ Error executing plan', isStreaming: false }
          : m
      ));
    } finally {
      this.messages.update(msgs => msgs.map(m =>
        m.id === assistantId ? { ...m, content: m.content.trimEnd(), isStreaming: false } : m
      ));
      this.isApproving.set(false);
      this.isGenerating.set(false);
      this.hasPendingPlan.set(false);
      this.currentAbortController = null;
    }
  }

  rejectPlan(): void {
    const sessionId = this.activeSessionId();
    if (!sessionId) return;

    this.chatService.rejectPlan(sessionId).subscribe({
      next: () => {
        this.hasPendingPlan.set(false);
        this.pendingPlanContent.set(null);
        this.currentMode.set('planning');
        console.log('Plan rejected');
      },
      error: (error) => {
        console.error('Error rejecting plan:', error);
      }
    });
  }

  requestChanges(): void {
    this.showFeedbackInput.set(true);
  }

  cancelFeedback(): void {
    this.showFeedbackInput.set(false);
    this.planFeedback.set('');
  }

  async submitFeedback(): Promise<void> {
    const sessionId = this.activeSessionId();
    const feedback = this.planFeedback();
    if (!sessionId || !feedback.trim()) return;

    this.isGenerating.set(true);
    this.showFeedbackInput.set(false);
    this.currentAbortController = new AbortController();

    // Clear old plan content and show loading state
    this.hasPendingPlan.set(true); // Keep true to show the card
    this.pendingPlanContent.set(null); // Clear content to show loading
    this.planFeedback.set(''); // Clear feedback immediately

    try {
      const stream = this.chatService.regeneratePlanStream(
        sessionId,
        feedback,
        this.currentAbortController.signal
      );

      let planText = '';
      for await (const event of stream) {
        console.log('[REGEN DEBUG] Event received:', event.type, event);

        // Handle all text event types - matching sendActualMessage logic
        if (event.type === 'data' && event.data?.text) {
          // Primary case: Backend sends {type: 'data', data: {text: ...}}
          planText += event.data.text;
          this.pendingPlanContent.set(planText);
        } else if (event.type === 'text' && event.data?.content) {
          // Alternate case: {type: 'text', data: {content: ...}}
          planText += event.data.content;
          this.pendingPlanContent.set(planText);
        } else if (event.type === 'text' && event.data?.text) {
          // Another alternate: {type: 'text', data: {text: ...}}
          planText += event.data.text;
          this.pendingPlanContent.set(planText);
        } else if (event.type === 'text' && event.content) {
          // Legacy format: {type: 'text', content: ...}
          planText += event.content;
          this.pendingPlanContent.set(planText);
        } else if (event.type === 'done') {
          console.log('[REGEN DEBUG] Done event, planText length:', planText.length);
          // If we received plan content, keep the card visible
          // This is the key fix: prioritize having content over the done event flag
          if (planText.trim()) {
            this.hasPendingPlan.set(true);
            this.pendingPlanContent.set(planText);
            console.log('[REGEN DEBUG] Plan set successfully');
          } else {
            // Only hide if we truly got no content
            const doneData = event.data || event;
            console.log('[REGEN DEBUG] Done data:', doneData);
            if (!doneData.has_pending_plan) {
              this.hasPendingPlan.set(false);
              this.pendingPlanContent.set(null);
            }
          }
        }
      }
    } catch (error) {
      console.error('Error regenerating plan:', error);
      // Show error in the plan card area
      this.pendingPlanContent.set('❌ Error regenerating plan: ' + (error instanceof Error ? error.message : 'Unknown error'));
    } finally {
      this.isGenerating.set(false);
      this.currentAbortController = null;
    }

  }

  toggleMode(): void {
    this.currentMode.update(mode => {
      if (mode === 'learning') return 'planning';
      if (mode === 'planning') return 'execution';
      return 'learning';
    });
  }

  // === Auth Modal Methods ===

  openAuthModal(): void {
    this.authModalMode.set('login');
    this.authForm = { email: '', password: '', otpToken: '' };
    this.authError.set(null);
    this.magicLinkEmail.set(null);
    this.authModalOpen.set(true);
  }

  closeAuthModal(): void {
    this.authModalOpen.set(false);
    this.authError.set(null);
  }

  switchAuthMode(): void {
    this.authModalMode.update(mode => mode === 'login' ? 'signup' : 'login');
    this.authError.set(null);
  }

  submitAuth(): void {
    const { email, password } = this.authForm;
    if (!email || !password) return;

    this.authError.set(null);

    if (this.authModalMode() === 'login') {
      this.authService.login(email, password).subscribe(result => {
        if (result.success) {
          this.closeAuthModal();
        } else {
          this.authError.set(result.error || 'Login failed');
        }
      });
    } else {
      this.authService.signup(email, password).subscribe(result => {
        if (result.success) {
          // After signup, switch to login
          this.authModalMode.set('login');
          this.authError.set(null);
          // Show success message briefly
          alert(result.message || 'Account created! Please check your email for confirmation.');
        } else {
          this.authError.set(result.error || 'Signup failed');
        }
      });
    }
  }

  // === Credits Page Method ===

  /**
   * Open the credits purchase page on the website.
   * Purchases are handled through the web for security and simplicity.
   */
  openCreditsPage(): void {
    console.log('[App] openCreditsPage called');
    // Open the credits page in the default browser using the desktop service bridge
    this.desktopService.openUrl('https://godoty.app/#pricing');
  }

  // === Account Menu Methods ===

  openAccountMenu(): void {
    // For now, just logout - could expand to dropdown menu
    if (confirm('Sign out of your account?')) {
      this.authService.logout().subscribe(() => {
        // Auth state will be updated by the service
      });
    }
  }

  // === Insufficient Credits Modal ===

  showInsufficientCreditsModal(): void {
    this.insufficientCreditsOpen.set(true);
  }

  closeInsufficientCreditsModal(): void {
    this.insufficientCreditsOpen.set(false);
  }

  /**
   * Handle 402 errors from API responses
   */
  handleInsufficientCredits(): void {
    this.isGenerating.set(false);
    this.showInsufficientCreditsModal();
  }

  // === OAuth and Magic Link Methods ===

  sendMagicLink(): void {
    const email = this.authForm.email;
    if (!email) return;

    this.authService.sendMagicLink(email).subscribe(result => {
      if (result.success) {
        this.authError.set(null);
        // Store email for OTP verification and switch to OTP mode
        this.magicLinkEmail.set(email);
        this.authModalMode.set('otp');
      } else {
        this.authError.set(result.error || 'Failed to send magic link');
      }
    });
  }

  verifyOTP(): void {
    const email = this.magicLinkEmail() || this.authForm.email;
    const token = this.authForm.otpToken;
    if (!email || !token) return;

    this.authService.verifyOTP(email, token).subscribe(result => {
      if (result.success) {
        this.closeAuthModal();
      } else {
        this.authError.set(result.error || 'Invalid or expired code');
      }
    });
  }

  backToLogin(): void {
    this.authModalMode.set('login');
    this.authError.set(null);
    this.authForm.otpToken = '';
  }

  signInWithOAuth(provider: string): void {
    // Desktop Flow: Redirect to backend callback page so system browser can handle it
    const callbackUrl = `${window.location.origin}/api/auth/callback-html`;

    this.authService.signInWithOAuth(provider, callbackUrl).subscribe(result => {
      if (result.success) {
        // OAuth flow opened in browser - close modal
        this.closeAuthModal();

        // Start polling for session via backend since we are in a desktop app/webview
        // and cannot easily intercept the system browser callback
        this.authService.pollAuthStatus().subscribe();
      } else {
        this.authError.set(result.error || `${provider} sign-in failed`);
      }
    });
  }
}