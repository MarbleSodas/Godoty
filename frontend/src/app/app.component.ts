import { Component, signal, computed, effect, ViewChild, ElementRef, AfterViewChecked, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { ChatService, Message, Session, ToolCall, ExecutionPlan, WorkflowMetrics } from './services/chat.service';
import { DesktopService } from './services/desktop.service';

interface SessionMetrics {
  totalTokens: number;
  promptTokens: number;
  completionTokens: number;
  sessionCost: number;
  projectTotalCost: number;
  toolCalls: number;
  toolErrors: number;
  generationTimeMs?: number;
}

interface AgentConfig {
  projectPath: string;
  planningModel: string;
  executorModel: string;
  openRouterKey: string;
  status: 'idle' | 'working' | 'stopped' | 'paused';
  showSettings: boolean;
  godotVersion: string;
  godotConnected: boolean;
  connectionState: 'connected' | 'disconnected' | 'connecting' | 'error';
  mode: 'planning' | 'fast';
}

interface GroupedEvent {
  type: 'text_block' | 'tool';
  content?: string;
  toolCall?: ToolCall;
  sequence: number;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="flex h-screen w-full bg-[#212529] text-slate-200 font-sans overflow-hidden selection:bg-[#478cbf] selection:text-white">
      
      <!-- Sidebar -->
      <aside class="w-72 flex-shrink-0 flex flex-col border-r border-[#363d4a] bg-[#212529]">
        <!-- Header / Logo -->
        <div class="p-4 border-b border-[#363d4a] flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-8 h-8 rounded bg-[#478cbf] flex items-center justify-center shadow-lg shadow-blue-900/20">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h1 class="font-bold text-lg tracking-tight text-white">Godoty</h1>
          </div>
          
          <!-- Settings Toggle (Menu) -->
          <button (click)="toggleSettings()" class="p-2 rounded hover:bg-[#363d4a] text-slate-400 hover:text-white transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>

        <!-- Session List (Takes remaining height) -->
        <div class="flex-1 overflow-y-auto p-2">
          <!-- New Session Button -->
          <div class="px-2 pb-3">
            <button
              (click)="createNewSession()"
              class="w-full bg-[#478cbf] hover:bg-[#3a7ca8] text-white rounded-lg px-3 py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-2 shadow-lg shadow-blue-900/20 transform active:scale-95">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
              </svg>
              <span>New Session</span>
            </button>
          </div>

          <div class="px-2 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">Sessions</div>
          
          <div class="space-y-1">
            @for (session of sessions(); track session.id) {
              <button 
                class="w-full text-left px-3 py-3 rounded-lg text-sm transition-all duration-200 group flex flex-col gap-1 relative pr-8"
                [class.bg-[#363d4a]]="session.active"
                [class.text-white]="session.active"
                [class.text-slate-400]="!session.active"
                [class.hover:bg-[#2b303b]]="!session.active"
                [class.hover:text-slate-200]="!session.active"
                (click)="selectSession(session.id)">
                
                <span class="font-medium truncate">{{ session.title }}</span>
                <div class="flex items-center justify-between w-full">
                    <span class="text-[10px] opacity-60">{{ session.date | date:'shortTime' }}</span>
                    @if (session.metrics) {
                        <div class="flex items-center gap-2 text-[10px] font-mono opacity-60">
                           <span>{{ session.metrics.session_tokens | number }}t</span>
                           <span>$ {{ session.metrics.session_cost.toFixed(3) }}</span>
                        </div>
                    }
                </div>
                
                <!-- Remove Button -->
                <div class="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
                   <div (click)="$event.stopPropagation(); removeSession(session.id)" 
                        class="p-1.5 rounded hover:bg-red-500/20 hover:text-red-400 text-slate-500 transition-colors cursor-pointer"
                        title="Remove from history">
                      <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                   </div>
                </div>
              </button>
            }
          </div>
        </div>

        <!-- Metrics Panel (Fixed at bottom of sidebar) -->
        <div class="p-4 bg-[#1d2125] border-t border-[#363d4a]">
          <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Session
          </div>
          
          <div class="space-y-3">
            <div class="flex justify-between items-baseline">
              <span class="text-[11px] text-slate-400">Cost</span>
              <span class="font-mono text-sm text-white">\${{ metrics().sessionCost.toFixed(4) }}</span>
            </div>

            <div class="flex justify-between items-baseline">
               <span class="text-[11px] text-slate-400">Tokens</span>
               <span class="font-mono text-sm text-[#478cbf]">{{ metrics().totalTokens | number }}</span>
            </div>


          </div>

          <!-- Project Metrics -->
          @if (projectMetrics()) {
             <div class="mt-4 pt-3 border-t border-[#363d4a] space-y-3">
                <div class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                    </svg>
                    Project
                </div>
                
                <div class="flex justify-between items-baseline">
                   <span class="text-[11px] text-slate-400">Total Cost</span>
                   <span class="font-mono text-sm text-white">\${{ projectMetrics()?.total_cost | number:'1.2-4' }}</span>
                </div>
                
                <div class="flex justify-between items-baseline">
                   <span class="text-[11px] text-slate-400">Total Tokens</span>
                   <span class="font-mono text-sm text-[#478cbf]">{{ projectMetrics()?.total_tokens | number }}</span>
                </div>

                 <div class="flex justify-between items-baseline">
                   <span class="text-[11px] text-slate-400">Sessions</span>
                   <span class="font-mono text-sm text-slate-300">{{ projectMetrics()?.total_sessions }}</span>
                </div>
             </div>
          }
        </div>
        
        <!-- Footer -->
        <div class="p-3 border-t border-[#363d4a] text-[10px] text-slate-500 flex justify-between bg-[#1a1d21]">
           <span [title]="config().projectPath" class="truncate max-w-[150px]">{{ config().projectPath.split('/').pop() || 'No Project' }}</span>
           <span class="flex items-center gap-1"
                 [title]="config().connectionState === 'connected' ? 'Connected to Godot' :
                          config().connectionState === 'connecting' ? 'Connecting to Godot...' :
                          config().connectionState === 'error' ? 'Connection Error' : 'Disconnected'">
             <span class="w-1.5 h-1.5 rounded-full"
                   [class.bg-green-500]="config().connectionState === 'connected'"
                   [class.bg-yellow-500]="config().connectionState === 'connecting'"
                   [class.bg-red-500]="config().connectionState === 'disconnected' || config().connectionState === 'error'"
                   [class.animate-pulse]="config().connectionState === 'connecting'"></span>
             {{ config().godotVersion || 'v4.x' }}
           </span>
        </div>
      </aside>

      <!-- Main Chat Area -->
      <main class="flex-1 flex flex-col relative bg-[#1a1d21]">
        
        <!-- Settings Overlay (Configuration Menu) -->
        @if (config().showSettings) {
          <div class="absolute inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
            <div class="bg-[#2b303b] border border-[#363d4a] rounded-xl shadow-2xl w-[500px] p-6 animate-in fade-in slide-in-from-top-2">
              <div class="flex justify-between items-center mb-6 border-b border-[#363d4a] pb-4">
                <h3 class="font-bold text-white text-lg">Configuration</h3>
                <button (click)="toggleSettings()" class="text-slate-400 hover:text-white transition-colors">
                  <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              
              <div class="space-y-5">
                <!-- Planning Model -->
                <div>
                  <label class="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Planning Agent Model</label>
                  <select 
                    [ngModel]="config().planningModel" 
                    (ngModelChange)="updateConfigField('planningModel', $event)"
                    class="w-full bg-[#1a1d21] border border-[#363d4a] rounded-lg px-3 py-2.5 text-sm text-white focus:ring-1 focus:ring-[#478cbf] focus:border-[#478cbf] outline-none transition-all appearance-none">
                    @for (option of modelOptions; track option.id) {
                      <option [value]="option.id">{{ option.name }}</option>
                    }
                  </select>
                </div>

                <!-- Executor Model -->
                <div>
                  <label class="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Executor Agent Model</label>
                  <select 
                    [ngModel]="config().executorModel" 
                    (ngModelChange)="updateConfigField('executorModel', $event)"
                    class="w-full bg-[#1a1d21] border border-[#363d4a] rounded-lg px-3 py-2.5 text-sm text-white focus:ring-1 focus:ring-[#478cbf] focus:border-[#478cbf] outline-none transition-all appearance-none">
                    @for (option of modelOptions; track option.id) {
                      <option [value]="option.id">{{ option.name }}</option>
                    }
                  </select>
                </div>

                <!-- API Key -->
                <div>
                  <label class="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">OpenRouter API Key</label>
                  <div class="relative">
                    <input 
                      type="password" 
                      [ngModel]="config().openRouterKey" 
                      (ngModelChange)="updateConfigField('openRouterKey', $event)"
                      placeholder="sk-or-..."
                      class="w-full bg-[#1a1d21] border border-[#363d4a] rounded-lg px-3 py-2.5 text-sm text-white focus:ring-1 focus:ring-[#478cbf] focus:border-[#478cbf] outline-none transition-all placeholder-slate-600">
                  </div>
                  <p class="text-[10px] text-slate-500 mt-1.5">Key is stored locally in your project configuration.</p>
                </div>

                <!-- Project Path (Read-only) -->
                <div>
                  <label class="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Project Path</label>
                  <div class="w-full bg-[#1a1d21] border border-[#363d4a] rounded-lg px-3 py-2.5 text-xs text-slate-400 font-mono truncate opacity-75 select-all">
                    {{ config().projectPath }}
                  </div>
                </div>
              </div>

              <!-- Footer Actions -->
              <div class="mt-8 pt-4 border-t border-[#363d4a] flex justify-end gap-3">
                <button (click)="toggleSettings()" class="px-4 py-2 rounded-lg text-sm font-medium text-slate-300 hover:text-white hover:bg-[#363d4a] transition-colors">
                  Cancel
                </button>
                <button (click)="saveSettings()" class="px-4 py-2 rounded-lg text-sm font-medium text-white bg-[#478cbf] hover:bg-[#3a7ca8] shadow-lg shadow-blue-900/20 transition-all transform active:scale-95">
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        }

        <!-- Top Bar (Minimal) -->
        <div class="h-14 border-b border-[#363d4a] flex items-center justify-between px-6 bg-[#212529]/50 backdrop-blur supports-[backdrop-filter]:bg-[#212529]/50 sticky top-0 z-10">
          <div class="flex items-center gap-2">
             <span class="text-sm font-medium text-slate-300">{{ getCurrentSessionTitle() }}</span>
          </div>
          <div class="flex items-center gap-4 text-slate-400">
             <button class="hover:text-white transition-colors text-xs uppercase tracking-wider font-medium">Export</button>

             <!-- Task Sidebar Toggle -->
             @if (currentPlan()) {
               <button
                 (click)="toggleTaskSidebar()"
                 class="flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all duration-200 hover:bg-[#363d4a]"
                 [class.bg-[#478cbf]/10]="taskSidebarOpen()"
                 [class.text-[#478cbf]]="taskSidebarOpen()"
                 title="Toggle Task List">
                 <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                   <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                 </svg>
                 <span class="text-xs font-medium hidden md:inline">Tasks</span>
               </button>
             }
          </div>
        </div>

        <!-- Messages Container -->
        <div class="flex-1 overflow-y-auto p-4 md:p-8 space-y-4 scroll-smooth" #scrollContainer>
          
          <!-- Welcome Message -->
          @if (messages().length === 0 && !currentSessionId()) {
            <div class="flex flex-col items-center justify-center py-10 text-center opacity-60">
               <div class="w-12 h-12 rounded bg-[#363d4a] flex items-center justify-center mb-4">
                 <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-[#478cbf]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
               </div>
               <h2 class="text-lg font-medium text-white">Godoty Agent Ready</h2>
               <p class="text-sm text-slate-400 max-w-md mt-2">
                 I have analyzed the project structure at <code>{{config().projectPath}}</code>.
                 I can help you refactor GDScript, create new scenes, or debug signals.
               </p>
               <p class="text-sm text-slate-500 max-w-md mt-3">
                 Click "New Session" to start a conversation or continue with an existing session.
               </p>
            </div>
          } @else if (messages().length === 0 && currentSessionId()) {
            <div class="flex flex-col items-center justify-center py-10 text-center opacity-60">
               <div class="w-12 h-12 rounded bg-[#363d4a] flex items-center justify-center mb-4">
                 <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-[#478cbf]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                  </svg>
               </div>
               <h2 class="text-lg font-medium text-white">Ready to Chat</h2>
               <p class="text-sm text-slate-400 max-w-md mt-2">
                 Start a conversation by sending a message below.
               </p>
            </div>
          }

          @for (msg of messages(); track msg.id) {
            <div class="w-full max-w-3xl mx-auto flex gap-4 group" [class.flex-row-reverse]="msg.role === 'user'">
              
              <!-- Avatar -->
              <div class="flex-shrink-0 w-8 h-8 rounded flex items-center justify-center"
                   [class.bg-[#478cbf]]="msg.role === 'assistant'"
                   [class.bg-slate-600]="msg.role === 'user'">
                 @if (msg.role === 'assistant') {
                   <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.384-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
                    </svg>
                 } @else {
                   <span class="text-xs font-bold text-white">YOU</span>
                 }
              </div>

              <!-- Content -->
              <div class="flex flex-col max-w-[85%]" [class.items-end]="msg.role === 'user'">
                <div class="relative px-4 py-4 rounded-2xl text-sm shadow-sm"
                     [class.bg-[#2b303b]]="msg.role === 'assistant'"
                     [class.text-slate-200]="msg.role === 'assistant'"
                     [class.rounded-tl-none]="msg.role === 'assistant'"
                     [class.bg-[#3d4452]]="msg.role === 'user'"
                     [class.text-white]="msg.role === 'user'"
                     [class.rounded-tr-none]="msg.role === 'user'">

                  <!-- Show thinking indicator when streaming with no content yet -->
                  @if (msg.isStreaming && !msg.content && msg.toolCalls?.length === 0 && !msg.plan) {
                    <div class="flex items-center gap-2 text-slate-400 italic">
                      <div class="flex gap-1">
                        <span class="w-2 h-2 bg-[#478cbf] rounded-full animate-bounce" style="animation-delay: 0ms"></span>
                        <span class="w-2 h-2 bg-[#478cbf] rounded-full animate-bounce" style="animation-delay: 150ms"></span>
                        <span class="w-2 h-2 bg-[#478cbf] rounded-full animate-bounce" style="animation-delay: 300ms"></span>
                      </div>
                    </div>
                  } @else {
                    <!-- Chronological Event Display (if events array exists) -->
                    @if (msg.events && msg.events.length > 0) {
                      @for (groupedEvent of getGroupedEvents(msg); track groupedEvent.sequence) {
                        @if (groupedEvent.type === 'text_block') {
                          <!-- Text block with simple formatting -->
                          <div class="whitespace-pre-wrap text-sm">{{ groupedEvent.content }}</div>
                        } @else if (groupedEvent.type === 'tool') {
                          <!-- Tool call (inline with chronological flow) -->
                          @if (groupedEvent.toolCall) {
                            <div class="my-0">
                              <div class="bg-[#1a1d21] rounded p-1.5 border border-[#363d4a] text-xs">
                                <div class="flex items-center justify-between mb-1.5">
                                  <div class="flex items-center gap-1.5">
                                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-[#478cbf]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                                    </svg>
                                    <span class="font-mono text-[#478cbf] font-medium">{{ groupedEvent.toolCall.name }}</span>
                                  </div>
                                  <span class="text-[10px] uppercase px-1.5 py-0.5 rounded font-medium"
                                        [class.bg-yellow-500/20]="groupedEvent.toolCall.status === 'running'"
                                        [class.text-yellow-500]="groupedEvent.toolCall.status === 'running'"
                                        [class.bg-green-500/20]="groupedEvent.toolCall.status === 'completed'"
                                        [class.text-green-500]="groupedEvent.toolCall.status === 'completed'"
                                        [class.bg-red-500/20]="groupedEvent.toolCall.status === 'failed'"
                                        [class.text-red-500]="groupedEvent.toolCall.status === 'failed'">
                                    {{ groupedEvent.toolCall.status }}
                                  </span>
                                </div>
                                @if (groupedEvent.toolCall.input && (groupedEvent.toolCall.input | json) !== '{}') {
                                  <div class="font-mono text-slate-500 text-[10px] opacity-75 mb-2">
                                    {{ groupedEvent.toolCall.input | json }}
                                  </div>
                                }
                                @if (groupedEvent.toolCall.result) {
                                  <div class="mt-1.5 pt-1.5 border-t border-[#363d4a] text-slate-400 font-mono text-[10px] max-h-24 overflow-y-auto">
                                    <span class="text-slate-600 block mb-1 uppercase font-semibold">Result:</span>
                                    <div class="text-slate-400">{{ groupedEvent.toolCall.result | json }}</div>
                                  </div>
                                }
                              </div>
                            </div>
                          }
                        }
                      }
                      <!-- Streaming indicator after all events -->
                      @if(msg.isStreaming) {
                        <span class="inline-block w-2 h-4 ml-1 bg-[#478cbf] animate-pulse align-middle"></span>
                      }
                    } @else {
                      <!-- Fallback to old display for backward compatibility -->
                      <div class="whitespace-pre-wrap text-sm">{{ filterExecutionPlanBlocks(msg.content) }}</div>

                      @if(msg.isStreaming) {
                        <span class="inline-block w-2 h-4 ml-1 bg-[#478cbf] animate-pulse align-middle"></span>
                      }

                      <!-- Tool Calls - Old display (kept for backward compatibility) -->
                      @if (msg.toolCalls && msg.toolCalls.length > 0) {
                        <div class="mt-3 space-y-2">
                          @for (tool of msg.toolCalls; track tool.name + $index) {
                            <div class="bg-[#1a1d21] rounded p-2.5 border border-[#363d4a] text-xs">
                              <div class="flex items-center justify-between mb-1.5">
                                <div class="flex items-center gap-1.5">
                                  <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5 text-[#478cbf]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                                  </svg>
                                  <span class="font-mono text-[#478cbf] font-medium">{{ tool.name }}</span>
                                </div>
                                <span class="text-[10px] uppercase px-1.5 py-0.5 rounded font-medium"
                                      [class.bg-yellow-500/20]="tool.status === 'running'"
                                      [class.text-yellow-500]="tool.status === 'running'"
                                      [class.bg-green-500/20]="tool.status === 'completed'"
                                      [class.text-green-500]="tool.status === 'completed'"
                                      [class.bg-red-500/20]="tool.status === 'failed'"
                                      [class.text-red-500]="tool.status === 'failed'">
                                  {{ tool.status }}
                                </span>
                              </div>
                              @if (tool.input && (tool.input | json) !== '{}') {
                                <div class="font-mono text-slate-500 text-[10px] opacity-75 mb-1">
                                  {{ tool.input | json }}
                                </div>
                              }
                              @if (tool.result) {
                                <div class="mt-1.5 pt-1.5 border-t border-[#363d4a] text-slate-400 font-mono text-[10px] max-h-24 overflow-y-auto">
                                  <span class="text-slate-600 block mb-1 uppercase font-semibold">Result:</span>
                                  <div class="text-slate-400">{{ tool.result | json }}</div>
                                </div>
                              }
                            </div>
                          }
                        </div>
                      }
                    }
                  }
                </div>

                <!-- Message Metrics -->
                @if (!msg.isStreaming && msg.cost !== undefined) {
                  <div class="relative flex items-center gap-3 mt-1.5 px-1 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                     <div class="flex items-center gap-1 text-[10px] text-slate-500 font-mono cursor-help group/tooltip">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        <span>{{ msg.tokens }} tok</span>

                        <!-- Detailed tooltip -->
                        <div class="absolute bottom-full left-0 mb-2 w-64 bg-[#1a1d21] border border-[#363d4a] rounded-lg p-3 shadow-xl opacity-0 group-hover/tooltip:opacity-100 transition-opacity duration-200 pointer-events-none z-50">
                          <div class="space-y-2 text-xs">
                            @if (msg.modelName) {
                              <div class="flex justify-between">
                                <span class="text-slate-500">Model:</span>
                                <span class="text-slate-300 font-mono text-[10px]">{{ msg.modelName }}</span>
                              </div>
                            }
                            @if (msg.promptTokens !== undefined) {
                              <div class="flex justify-between">
                                <span class="text-slate-500">Prompt Tokens:</span>
                                <span class="text-[#478cbf] font-mono">{{ msg.promptTokens | number }}</span>
                              </div>
                            }
                            @if (msg.completionTokens !== undefined) {
                              <div class="flex justify-between">
                                <span class="text-slate-500">Completion Tokens:</span>
                                <span class="text-[#478cbf] font-mono">{{ msg.completionTokens | number }}</span>
                              </div>
                            }
                            <div class="flex justify-between pt-1 border-t border-[#363d4a]">
                              <span class="text-slate-500">Total Tokens:</span>
                              <span class="text-white font-mono font-semibold">{{ msg.tokens | number }}</span>
                            </div>
                            <div class="flex justify-between">
                              <span class="text-slate-500">Cost:</span>
                              <span class="text-green-400 font-mono">$ {{ msg.cost.toFixed(6) }}</span>
                            </div>
                            @if (msg.generationTimeMs) {
                              <div class="flex justify-between">
                                <span class="text-slate-500">Time:</span>
                                <span class="text-slate-300 font-mono">{{ msg.generationTimeMs }}ms</span>
                              </div>
                            }
                            @if (msg.workflowMetrics) {
                              <div class="pt-2 border-t border-[#363d4a]">
                                <div class="text-slate-400 font-semibold text-xs mb-2">Workflow Total</div>
                                <div class="flex justify-between">
                                  <span class="text-slate-500">Total:</span>
                                  <span class="text-white font-mono font-semibold">{{ msg.workflowMetrics.totalTokens }} tokens</span>
                                </div>
                                <div class="flex justify-between">
                                  <span class="text-slate-500">Cost:</span>
                                  <span class="text-green-400 font-mono">$ {{ msg.workflowMetrics.totalCost.toFixed(4) }}</span>
                                </div>
                              </div>
                            }
                          </div>
                        </div>
                     </div>
                     <div class="flex items-center gap-1 text-[10px] text-slate-500 font-mono">
                        <span>$</span>
                        <span>{{ msg.cost.toFixed(5) }}</span>
                     </div>
                  </div>
                }
              </div>
            </div>
          }

          <!-- Spacer for bottom scrolling -->
          <div class="h-32"></div>
        </div>

        <!-- Input Area -->
        <div class="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-[#1a1d21] via-[#1a1d21] to-transparent">
          <div class="max-w-3xl mx-auto bg-[#2b303b] border border-[#363d4a] rounded-xl shadow-2xl shadow-black/20 flex flex-col overflow-hidden focus-within:border-[#478cbf] transition-colors">
            
            <textarea 
              [(ngModel)]="userInput" 
              (keydown.enter)="onEnter($event)"
              [disabled]="config().status === 'working' && config().status !== 'stopped'"
              placeholder="Ask Godoty to generate code, analyze scenes, or optimize assets..."
              class="w-full bg-transparent border-0 text-white placeholder-slate-500 focus:ring-0 resize-none py-4 px-4 min-h-[60px] max-h-[200px] text-sm disabled:opacity-50"
              rows="1"
            ></textarea>
            
            <div class="flex items-center justify-between px-3 py-2 bg-[#2b303b] border-t border-[#363d4a]/50">
               <div class="flex items-center gap-2">
                 <button class="p-2 rounded hover:bg-[#363d4a] text-slate-400 hover:text-[#478cbf] transition-colors" title="Attach GDScript">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                    </svg>
                 </button>
                 <!-- Additional attachment options could go here -->
               </div>

               <!-- Mode Toggle -->
               <div class="flex items-center gap-2 mr-auto ml-2">
                  <button 
                    (click)="toggleMode()"
                    class="flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium transition-colors border"
                    [class.bg-blue-500/10]="config().mode === 'planning'"
                    [class.text-blue-400]="config().mode === 'planning'"
                    [class.border-blue-500/30]="config().mode === 'planning'"
                    [class.bg-purple-500/10]="config().mode === 'fast'"
                    [class.text-purple-400]="config().mode === 'fast'"
                    [class.border-purple-500/30]="config().mode === 'fast'">
                    
                    @if (config().mode === 'planning') {
                      <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                      </svg>
                      <span>Plan</span>
                    } @else {
                      <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      <span>Fast</span>
                    }
                  </button>
               </div>
               
               <div class="flex items-center gap-3">
                 @if (config().status !== 'working') {
                    <span class="text-[10px] text-slate-500 font-mono hidden sm:inline">
                        {{ userInput().length }} chars
                    </span>
                    <button 
                        (click)="sendMessage()" 
                        [disabled]="!userInput().trim()"
                        class="bg-[#478cbf] hover:bg-[#3a7ca8] disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg px-4 py-1.5 text-sm font-medium transition-colors flex items-center gap-2 shadow-lg shadow-blue-900/20">
                        <span>Send</span>
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                        </svg>
                    </button>
                 } @else {
                    <button 
                        (click)="stopAgent()" 
                        class="bg-[#d63e3e] hover:bg-[#b32d2d] text-white rounded-lg px-4 py-1.5 text-sm font-medium transition-colors flex items-center gap-2 shadow-lg shadow-red-900/20">
                        <span>Stop</span>
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 fill-current" viewBox="0 0 20 20">
                          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clip-rule="evenodd" />
                        </svg>
                    </button>
                 }
               </div>
            </div>
          </div>
          <div class="text-center mt-2">
            <p class="text-[10px] text-slate-600">Godoty can make mistakes. Review generated GDScript before running.</p>
          </div>
        </div>

      </main>

      <!-- Task Sidebar -->
      @if (currentPlan() && taskSidebarOpen()) {
        <!-- Backdrop (mobile only) -->
        <div class="fixed inset-0 bg-black/50 z-40 md:hidden" (click)="toggleTaskSidebar()"></div>

        <!-- Sidebar -->
        <aside class="w-80 border-l border-[#363d4a] bg-[#212529] flex flex-col overflow-hidden animate-in slide-in-from-right-2 duration-200 fixed md:relative right-0 top-0 h-full z-50 md:z-auto md:flex-shrink-0">
          <!-- Sidebar Header -->
          <div class="h-14 border-b border-[#363d4a] flex items-center justify-between px-4 bg-[#212529]/50 backdrop-blur">
            <div class="flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-[#478cbf]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
              <h2 class="text-sm font-semibold text-white">Execution Plan</h2>
            </div>
            <button
              (click)="toggleTaskSidebar()"
              class="p-1 rounded hover:bg-[#363d4a] text-slate-400 hover:text-white transition-colors"
              title="Close Tasks">
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <!-- Plan Title & Description -->
          <div class="px-4 py-3 border-b border-[#363d4a] bg-[#1a1d21]">
            <h3 class="text-sm font-medium text-white mb-1">{{ currentPlan()!.title }}</h3>
            @if (currentPlan()!.description) {
              <p class="text-xs text-slate-400 leading-relaxed">{{ currentPlan()!.description }}</p>
            }
            <div class="mt-2 flex items-center gap-2 text-[10px] text-slate-500">
              <span>{{ currentPlan()!.steps.length }} steps</span>
              <span class="w-1 h-1 bg-slate-600 rounded-full"></span>
              <span class="uppercase px-1.5 py-0.5 rounded"
                    [class.bg-blue-500/20]="currentPlan()!.status === 'pending'"
                    [class.text-blue-400]="currentPlan()!.status === 'pending'"
                    [class.bg-yellow-500/20]="currentPlan()!.status === 'running'"
                    [class.text-yellow-400]="currentPlan()!.status === 'running'"
                    [class.bg-green-500/20]="currentPlan()!.status === 'completed'"
                    [class.text-green-400]="currentPlan()!.status === 'completed'">
                {{ currentPlan()!.status }}
              </span>
            </div>
          </div>

          <!-- Steps List -->
          <div class="flex-1 overflow-y-auto p-2">
            <div class="space-y-1">
              @for (step of currentPlan()!.steps; track step.id; let idx = $index) {
                <div class="p-3 rounded-lg border transition-all duration-200"
                     [class.border-[#363d4a]]="step.status === 'pending'"
                     [class.bg-transparent]="step.status === 'pending'"
                     [class.border-[#478cbf]/30]="step.status === 'running'"
                     [class.bg-[#478cbf]/5]="step.status === 'running'"
                     [class.border-green-500/30]="step.status === 'completed'"
                     [class.bg-green-500/5]="step.status === 'completed'"
                     [class.border-red-500/30]="step.status === 'failed'"
                     [class.bg-red-500/5]="step.status === 'failed'">

                  <!-- Step Header -->
                  <div class="flex items-start gap-2 mb-2">
                    <!-- Status Icon -->
                    <div class="flex-shrink-0 mt-0.5">
                      @if (step.status === 'completed') {
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-green-500" viewBox="0 0 20 20" fill="currentColor">
                          <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                        </svg>
                      } @else if (step.status === 'running') {
                        <div class="w-4 h-4 border-2 border-[#478cbf] border-t-transparent rounded-full animate-spin"></div>
                      } @else if (step.status === 'failed') {
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-red-500" viewBox="0 0 20 20" fill="currentColor">
                          <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd" />
                        </svg>
                      } @else {
                        <div class="w-4 h-4 rounded-full border-2 border-slate-600"></div>
                      }
                    </div>

                    <!-- Step Number & Title -->
                    <div class="flex-1 min-w-0">
                      <div class="flex items-baseline gap-1.5">
                        <span class="text-[10px] font-mono text-slate-500 font-semibold">{{ idx + 1 }}.</span>
                        <h4 class="text-xs font-medium text-white truncate">{{ step.title }}</h4>
                      </div>
                    </div>
                  </div>

                  <!-- Step Description -->
                  @if (step.description) {
                    <p class="text-[11px] text-slate-400 leading-relaxed ml-6 mb-2">{{ step.description }}</p>
                  }

                  <!-- Tool Calls (if any) -->
                  @if (step.tool_calls && step.tool_calls.length > 0) {
                    <div class="ml-6 mt-2 space-y-1">
                      @for (tool of step.tool_calls; track tool.name + $index) {
                        <div class="flex items-center gap-1.5 text-[10px]">
                          <svg xmlns="http://www.w3.org/2000/svg" class="h-3 w-3 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                          </svg>
                          <span class="font-mono text-slate-500">{{ tool.name }}</span>
                        </div>
                      }
                    </div>
                  }
                </div>
              }
            </div>
          </div>

          <!-- Sidebar Footer (optional stats) -->
          <div class="border-t border-[#363d4a] px-4 py-2 bg-[#1a1d21]">
            <div class="flex justify-between text-[10px] text-slate-500">
              <span>Progress</span>
              <span>{{ getCompletedStepsCount() }} / {{ currentPlan()!.steps.length }}</span>
            </div>
            <div class="mt-1 w-full bg-[#2b303b] h-1 rounded-full overflow-hidden">
              <div class="bg-green-500 h-full rounded-full transition-all duration-300"
                   [style.width.%]="getProgressPercentage()"></div>
            </div>
          </div>
        </aside>
      }
    </div>
  `,
  styles: [`
    /* Custom Scrollbar for that IDE feel */
    ::-webkit-scrollbar {
      width: 8px;
      height: 8px;
    }
    ::-webkit-scrollbar-track {
      background: #212529; 
    }
    ::-webkit-scrollbar-thumb {
      background: #363d4a; 
      border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: #478cbf; 
    }
    
    /* Animation utilities */
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    @keyframes slideDown { from { transform: translateY(-10px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
    @keyframes slideRight { from { transform: translateX(20px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    @keyframes textFadeUp { from { transform: translateY(4px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }

    .animate-in { animation: fadeIn 0.2s ease-out; }
    .slide-in-from-top-2 { animation: slideDown 0.2s ease-out; }
    .slide-in-from-right-2 { animation: slideRight 0.2s ease-out; }
    .slide-in-from-bottom { animation: textFadeUp 0.25s ease-out; }
  `]
})
export class App implements AfterViewChecked, OnInit {
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  // Model Options
  allowedModels = {
    "Gemini 3 Pro": "google/gemini-3-pro-preview",
    "Grok 4.1 Fast": "x-ai/grok-4.1-fast",
    "Sonnet 4.5": "anthropic/claude-sonnet-4.5",
    "Haiku 4.5": "anthropic/claude-haiku-4.5",
    "Minimax M2": "minimax/minimax-m2",
    "GPT 5.1 Codex": "openai/gpt-5.1-codex",
    "GLM 4.6": "z-ai/glm-4.6"
  };

  modelOptions = Object.entries(this.allowedModels).map(([name, id]) => ({ name, id }));

  // Signals for Reactive State
  userInput = signal('');
  messages = signal<Message[]>([]);

  // Session State
  sessions = signal<Session[]>([]);
  currentSessionId = signal<string | null>(null);

  config = signal<AgentConfig>({
    projectPath: '',
    planningModel: 'google/gemini-3-pro-preview',
    executorModel: 'anthropic/claude-sonnet-4.5',
    openRouterKey: '',
    status: 'idle',
    showSettings: false,
    godotVersion: '',
    godotConnected: false,
    connectionState: 'disconnected',
    mode: 'planning'
  });

  metrics = signal<SessionMetrics>({
    totalTokens: 0,
    promptTokens: 0,
    completionTokens: 0,
    sessionCost: 0.00,
    projectTotalCost: 0.00,
    toolCalls: 0,
    toolErrors: 0,
    generationTimeMs: undefined
  });

  projectMetrics = signal<any>(null);

  // Task list sidebar state
  taskSidebarOpen = signal(false);

  // Computed: Get current active plan from messages
  currentPlan = computed(() => {
    const msgs = this.messages();
    // Find the most recent assistant message with a plan
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === 'assistant' && msgs[i].plan) {
        return msgs[i].plan;
      }
    }
    return null;
  });

  private abortController: AbortController | null = null;

  constructor(
    private chatService: ChatService,
    private desktopService: DesktopService
  ) { }

  ngOnInit() {
    this.loadSessions();
    this.loadSystemInfo();
    this.loadAgentConfig();
    this.chatService.projectMetrics$.subscribe(m => this.projectMetrics.set(m));
  }

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  // ...

  private updateGodotConfig(status: any) {
    const connectionState = status.state || 'disconnected';
    const isConnected = connectionState === 'connected';
    const version = status.godot_version || '';
    const path = status.project_path || '';

    console.log('[App] Updating config - State:', connectionState, 'Connected:', isConnected, 'Version:', version, 'Path:', path);

    // Check if project path changed
    if (path && path !== this.config().projectPath) {
      console.log(`[App] Project path changed: ${path}`);

      // Clear current session - it belongs to old project
      this.currentSessionId.set(null);
      this.messages.set([]);

      // Update path and reload sessions
      this.chatService.setProjectPath(path);
      this.loadSessions();
    }

    this.config.update(c => ({
      ...c,
      godotConnected: isConnected,
      connectionState: connectionState,
      godotVersion: version,
      projectPath: path || c.projectPath
    }));
  }

  removeSession(sessionId: string) {
    if (confirm('Are you sure you want to remove this session from history?')) {
      this.chatService.hideSession(sessionId).subscribe(() => {
        this.sessions.update(list => list.filter(s => s.id !== sessionId));
        if (this.currentSessionId() === sessionId) {
          this.currentSessionId.set(null);
          this.messages.set([]);
        }
      });
    }
  }


  loadSessions() {
    this.chatService.listSessions().subscribe(sessions => {
      const currentId = this.currentSessionId();

      // If we have an active session that isn't in the new list (e.g. just switched project),
      // keep it visible so we don't lose context. It will be saved to the project DB on next message.
      if (currentId && !sessions.find(s => s.id === currentId)) {
        const existing = this.sessions().find(s => s.id === currentId);
        if (existing) {
          console.log(`[App] Preserving active session ${currentId} in list despite project switch`);
          sessions.unshift(existing);
        }
      }

      this.sessions.set(sessions);
      // Don't auto-select session on load - let user explicitly create or select a session
      // This allows the app to start in an empty state as requested
      // Don't auto-create session if empty - wait for first message or explicit session creation
    });
  }

  createNewSession(title?: string) {
    const newId = 'session-' + Date.now();
    const sessionTitle = title || 'New Session';

    // Clear current state immediately for better UX
    this.messages.set([]);
    this.currentSessionId.set(null);

    this.chatService.createSession(newId, sessionTitle).subscribe(() => {
      this.loadSessions();
      this.selectSession(newId);

      // Focus on input field after session creation
      setTimeout(() => {
        const textarea = document.querySelector('textarea') as HTMLTextAreaElement;
        if (textarea) {
          textarea.focus();
        }
      }, 100);
    });
  }

  selectSession(id: string) {
    this.currentSessionId.set(id);
    this.sessions.update(s => s.map(session => ({
      ...session,
      active: session.id === id
    })));

    // Load conversation history
    this.loadSessionHistory(id);
  }

  /**
   * Load full conversation history for a session from the backend.
   */
  private loadSessionHistory(sessionId: string) {
    // Clear current messages first to show loading state
    this.messages.set([]);

    // Reset metrics to avoid carrying over from previous session
    this.metrics.set({
      totalTokens: 0,
      promptTokens: 0,
      completionTokens: 0,
      sessionCost: 0,
      projectTotalCost: this.metrics().projectTotalCost, // Preserve project total
      toolCalls: 0,
      toolErrors: 0,
      generationTimeMs: undefined
    });

    // Fetch session details including chat history
    this.chatService.getSession(sessionId).subscribe({
      next: (response) => {
        if (response.status === 'success' && response.chat_history) {
          // Transform database format to frontend Message format using the enhanced method
          const messages: Message[] = this.transformSessionData(response.chat_history);
          this.messages.set(messages);

          // Apply or calculate metrics
          if (response.metrics) {
            this.metrics.set(response.metrics);
          } else {
            this.metrics.set(this.calculateMetricsFromMessages(messages));
          }

          console.log(`Loaded ${messages.length} messages for session ${sessionId}`);
        } else {
          // User notification for empty or error sessions
          console.warn(`Session ${sessionId} is empty or could not be loaded:`, response.message);
          this.messages.set([{
            id: 'system-empty',
            role: 'system',
            content: `This session appears to be empty or could not be loaded properly. You can start a new conversation here.`,
            timestamp: new Date()
          }]);
        }
      },
      error: (err) => {
        console.error('Failed to load session history:', err);

        // User notification for loading failures
        if (err.status === 404) {
          // Session not found - remove from list
          console.warn(`Session ${sessionId} not found, removing from list`);
          this.sessions.update(list => list.filter(s => s.id !== sessionId));
          this.currentSessionId.set(null);
          this.messages.set([{
            id: 'system-not-found',
            role: 'system',
            content: `This session could not be found. It may have been deleted or moved.`,
            timestamp: new Date()
          }]);
        } else {
          // General loading error
          this.messages.set([{
            id: 'system-error',
            role: 'system',
            content: `Unable to load this session. Please try again or select a different session.`,
            timestamp: new Date()
          }]);
        }
      }
    });
  }

  /**
   * Calculate aggregated metrics from message array.
   * Used as fallback when backend metrics unavailable.
   */
  private calculateMetricsFromMessages(messages: Message[]): SessionMetrics {
    const aggregated = messages.reduce((acc, msg) => {
      const toolCallsCount = msg.toolCalls?.length || 0;
      const toolErrorsCount = msg.toolCalls?.filter(tc => tc.status === 'failed').length || 0;

      return {
        totalTokens: acc.totalTokens + (msg.tokens || 0),
        promptTokens: acc.promptTokens + (msg.promptTokens || 0),
        completionTokens: acc.completionTokens + (msg.completionTokens || 0),
        sessionCost: acc.sessionCost + (msg.cost || 0),
        toolCalls: acc.toolCalls + toolCallsCount,
        toolErrors: acc.toolErrors + toolErrorsCount
      };
    }, {
      totalTokens: 0,
      promptTokens: 0,
      completionTokens: 0,
      sessionCost: 0,
      toolCalls: 0,
      toolErrors: 0
    });

    return {
      ...aggregated,
      projectTotalCost: this.metrics().projectTotalCost, // Preserve existing project total
      generationTimeMs: undefined
    };
  }

  /**
   * Transform session data from backend format to frontend Message format.
   * Handles both new events-based format and legacy content-based format.
   */
  private transformSessionData(chatHistory: any[]): Message[] {
    return chatHistory.map((msg: any, index: number) => {
      // Handle both new events-based format and legacy content-based format
      const baseMessage: Message = {
        id: msg.id || `${this.currentSessionId()}-${index}`,
        role: msg.role,
        content: msg.content || '',
        timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),

        // Token metrics (with backward compatibility)
        tokens: msg.tokens ?? 0,
        promptTokens: msg.promptTokens,
        completionTokens: msg.completionTokens,
        cost: msg.cost || 0,
        modelName: msg.modelName,
        generationTimeMs: msg.generationTimeMs,

        // Extended fields (preserved if present)
        toolCalls: msg.toolCalls,
        plan: msg.plan,
        workflowMetrics: msg.workflowMetrics,

        // Streaming state always false for historical messages
        isStreaming: false
      };

      // Handle new events-based format
      if (msg.events && Array.isArray(msg.events)) {
        return {
          ...baseMessage,
          events: msg.events
        };
      }

      // Handle legacy format or create minimal events array
      return {
        ...baseMessage,
        events: msg.content ? [{
          type: 'text',
          content: msg.content,
          timestamp: msg.timestamp || Date.now()
        }] : []
      };
    });
  }

  getCurrentSessionTitle() {
    return this.sessions().find(s => s.active)?.title || 'New Session';
  }

  toggleSettings() {
    this.config.update(c => ({ ...c, showSettings: !c.showSettings }));
  }

  toggleMode() {
    this.config.update(c => ({ ...c, mode: c.mode === 'planning' ? 'fast' : 'planning' }));
  }

  toggleTaskSidebar() {
    this.taskSidebarOpen.update(open => !open);
  }

  getCompletedStepsCount(): number {
    const plan = this.currentPlan();
    if (!plan) return 0;
    return plan.steps.filter(s => s.status === 'completed').length;
  }

  getProgressPercentage(): number {
    const plan = this.currentPlan();
    if (!plan || plan.steps.length === 0) return 0;
    return (this.getCompletedStepsCount() / plan.steps.length) * 100;
  }

  onEnter(event: Event) {
    event.preventDefault();
    this.sendMessage();
  }

  async sendMessage() {
    const text = this.userInput().trim();
    if (!text || this.config().status === 'working') return;

    let sessionId = this.currentSessionId();
    const isNewSession = !sessionId;

    // Explicit session creation - create session before sending first message
    if (isNewSession) {
      sessionId = 'session-' + Date.now();

      // Explicitly create session before sending message
      try {
        await firstValueFrom(
          this.chatService.createSession(sessionId, text)
        );
        this.currentSessionId.set(sessionId);
        console.log(`Created session ${sessionId} explicitly`);
      } catch (err) {
        console.error('Session creation failed:', err);
        return;  // Abort if creation fails
      }
    }

    // 1. Add User Message
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date(),
      tokens: 0,
      cost: 0
    };

    this.messages.update(msgs => [...msgs, userMsg]);
    this.userInput.set('');
    this.config.update(c => ({ ...c, status: 'working' }));

    // 2. Add Placeholder Assistant Message
    const aiMsgId = (Date.now() + 1).toString();
    const aiMsg: Message = {
      id: aiMsgId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
      tokens: 0,
      cost: 0,
      toolCalls: [],
      plan: undefined,
      events: []
    };
    this.messages.update(msgs => [...msgs, aiMsg]);

    try {
      // 3. Stream Response (sessionId is guaranteed to be non-null here)
      this.abortController = new AbortController();
      for await (const chunk of this.chatService.sendMessageStream(sessionId!, text, this.config().mode, this.abortController.signal)) {
        console.log('[AppComponent] Received chunk:', chunk); // DEBUG

        this.messages.update(msgs => msgs.map(m => {
          if (m.id !== aiMsgId) return m;

          const updatedMsg = { ...m };

          // Handle different event types
          console.log('[AppComponent] Processing event type:', chunk.type); // DEBUG
          switch (chunk.type) {
            case 'start':
              // Stream has started - show thinking indicator
              console.log('[AppComponent] Stream started');
              if (!updatedMsg.content) {
                updatedMsg.content = '';
              }
              break;

            case 'data':
              if (chunk.data?.text) {
                updatedMsg.content += chunk.data.text;
                // Add to chronological events
                if (!updatedMsg.events) updatedMsg.events = [];
                updatedMsg.events.push({
                  type: 'text',
                  timestamp: Date.now(),
                  sequence: updatedMsg.events.length,
                  content: chunk.data.text
                });
              }
              break;

            case 'reasoning':
              if (chunk.data?.text) {
                // For now, append reasoning to content with a special style or prefix
                // Or we could add a separate reasoning field to the message model
                // Let's just append it italicized for now
                updatedMsg.content += `\n*Thinking: ${chunk.data.text}*\n`;
              }
              break;

            case 'tool_use':
              if (!updatedMsg.toolCalls) updatedMsg.toolCalls = [];
              const newToolCall = {
                name: chunk.data.tool_name,
                input: chunk.data.tool_input,
                status: 'running' as const
              };
              updatedMsg.toolCalls.push(newToolCall);
              // Add to chronological events
              if (!updatedMsg.events) updatedMsg.events = [];
              updatedMsg.events.push({
                type: 'tool_use',
                timestamp: Date.now(),
                sequence: updatedMsg.events.length,
                toolCall: newToolCall
              });
              break;

            case 'tool_result':
              if (updatedMsg.toolCalls) {
                const toolCallIndex = updatedMsg.toolCalls.findIndex(t => t.name === chunk.data.tool_name && t.status === 'running');
                if (toolCallIndex !== -1) {
                  const oldToolCall = updatedMsg.toolCalls[toolCallIndex];
                  // Create a new toolCall object to trigger change detection
                  const newToolCall = {
                    ...oldToolCall,
                    status: 'completed' as const,
                    result: chunk.data.result,
                    input: (chunk.data.tool_input && (!oldToolCall.input || Object.keys(oldToolCall.input).length === 0))
                      ? chunk.data.tool_input
                      : oldToolCall.input
                  };
                  // Create new arrays to trigger change detection
                  updatedMsg.toolCalls = [
                    ...updatedMsg.toolCalls.slice(0, toolCallIndex),
                    newToolCall,
                    ...updatedMsg.toolCalls.slice(toolCallIndex + 1)
                  ];
                  // Update the existing tool_use event in the events array
                  if (updatedMsg.events) {
                    const toolEventIndex = updatedMsg.events.findIndex(e => e.type === 'tool_use' && e.toolCall?.name === chunk.data.tool_name);
                    if (toolEventIndex !== -1) {
                      updatedMsg.events = [
                        ...updatedMsg.events.slice(0, toolEventIndex),
                        {
                          ...updatedMsg.events[toolEventIndex],
                          toolCall: newToolCall
                        },
                        ...updatedMsg.events.slice(toolEventIndex + 1)
                      ];
                    }
                  }
                }
              }
              break;

            case 'plan_created':
              // Backend now sends full step details including titles and descriptions
              updatedMsg.plan = {
                title: chunk.data.title,
                description: chunk.data.description,
                steps: Array.isArray(chunk.data.steps)
                  ? chunk.data.steps.map((step: any) => ({
                    id: step.id,
                    title: step.title,
                    description: step.description,
                    tool_calls: step.tool_calls || [],
                    depends_on: step.depends_on || [],
                    status: step.status || 'pending'
                  }))
                  : [],
                status: 'pending'
              };
              break;

            case 'execution_started':
              // Execution has started
              console.log('[AppComponent] Execution started:', chunk.data);
              if (updatedMsg.plan) {
                updatedMsg.plan.status = 'running';
              }
              if (chunk.data?.message) {
                updatedMsg.content += chunk.data.message + '\n';
              }
              break;

            case 'execution_completed':
              // Execution has completed
              console.log('[AppComponent] Execution completed:', chunk.data);
              if (updatedMsg.plan) {
                updatedMsg.plan.status = 'completed';
              }
              if (chunk.data?.message) {
                updatedMsg.content += chunk.data.message + '\n';
              }
              break;

            case 'step_started':
              if (updatedMsg.plan) {
                // Use step_index from event data to find the exact step
                const stepIndex = chunk.data.step_index !== undefined
                  ? chunk.data.step_index
                  : updatedMsg.plan.steps.findIndex(s => s.id === chunk.data.step_id);

                if (stepIndex !== -1 && stepIndex < updatedMsg.plan.steps.length) {
                  updatedMsg.plan.steps[stepIndex].status = 'running';
                  // Update title/description if provided in event
                  if (chunk.data.title) {
                    updatedMsg.plan.steps[stepIndex].title = chunk.data.title;
                  }
                  if (chunk.data.description) {
                    updatedMsg.plan.steps[stepIndex].description = chunk.data.description;
                  }
                }
              }
              break;

            case 'step_completed':
              if (updatedMsg.plan) {
                // Use step_index or step_id to find the exact step
                const stepIndex = chunk.data.step_index !== undefined
                  ? chunk.data.step_index
                  : updatedMsg.plan.steps.findIndex(s => s.id === chunk.data.step_id);

                if (stepIndex !== -1 && stepIndex < updatedMsg.plan.steps.length) {
                  updatedMsg.plan.steps[stepIndex].status = chunk.data.status || 'completed';
                }
              }
              break;

            case 'step_failed':
              if (updatedMsg.plan) {
                // Use step_index or step_id to find the exact step
                const stepIndex = chunk.data.step_index !== undefined
                  ? chunk.data.step_index
                  : updatedMsg.plan.steps.findIndex(s => s.id === chunk.data.step_id);

                if (stepIndex !== -1 && stepIndex < updatedMsg.plan.steps.length) {
                  updatedMsg.plan.steps[stepIndex].status = 'failed';
                }
              }
              break;

            case 'tool_completed':
              // Executor tool completed
              if (updatedMsg.toolCalls) {
                const toolCallIndex = updatedMsg.toolCalls.findIndex(t => t.name === chunk.data.tool_name && t.status === 'running');
                if (toolCallIndex !== -1) {
                  const oldToolCall = updatedMsg.toolCalls[toolCallIndex];
                  const newStatus: 'completed' | 'failed' = chunk.data.success ? 'completed' : 'failed';
                  // Create a new toolCall object to trigger change detection
                  const newToolCall = {
                    ...oldToolCall,
                    status: newStatus
                  };
                  // Create new arrays to trigger change detection
                  updatedMsg.toolCalls = [
                    ...updatedMsg.toolCalls.slice(0, toolCallIndex),
                    newToolCall,
                    ...updatedMsg.toolCalls.slice(toolCallIndex + 1)
                  ];
                  // Update the existing tool_use event in the events array
                  if (updatedMsg.events) {
                    const toolEventIndex = updatedMsg.events.findIndex(e => e.type === 'tool_use' && e.toolCall?.name === chunk.data.tool_name);
                    if (toolEventIndex !== -1) {
                      updatedMsg.events = [
                        ...updatedMsg.events.slice(0, toolEventIndex),
                        {
                          ...updatedMsg.events[toolEventIndex],
                          toolCall: newToolCall
                        },
                        ...updatedMsg.events.slice(toolEventIndex + 1)
                      ];
                    }
                  }
                }
              }
              break;

            case 'workflow_metrics_complete':
              // Workflow metrics complete - aggregated planning + execution metrics
              console.log('[AppComponent] Workflow metrics complete:', chunk.data);
              if (chunk.data?.metrics) {
                const workflowMetrics: WorkflowMetrics = chunk.data.metrics;

                // Update the message with workflow metrics for display on hover
                updatedMsg.workflowMetrics = workflowMetrics;

                // Also update session metrics with the total workflow cost
                this.updateMetrics(
                  workflowMetrics.totalTokens,
                  0, // Don't break down prompt/completion for workflow metrics
                  0,
                  workflowMetrics.totalCost,
                  0, // Tool calls already tracked individually
                  0
                );
              }
              break;

            case 'end':
              // Stream has ended
              console.log('[AppComponent] Stream ended');
              break;

            case 'error':
              // Error occurred during streaming
              console.error('[AppComponent] Stream error:', chunk.data);
              if (chunk.data?.message) {
                updatedMsg.content += `\n\n⚠️ Error: ${chunk.data.message}`;
              } else if (chunk.data?.error) {
                updatedMsg.content += `\n\n⚠️ Error: ${JSON.stringify(chunk.data.error)}`;
              }
              if (updatedMsg.plan) {
                updatedMsg.plan.status = 'failed';
              }
              break;

            default:
              // Unknown event type - log it for debugging
              console.warn('[AppComponent] Unknown event type:', chunk.type, chunk);
              break;
          }

          // Handle metrics if present in any event
          if (chunk.data?.metrics) {
            const m = chunk.data.metrics;

            // Update message-specific metrics
            if (m.total_tokens) updatedMsg.tokens = m.total_tokens;
            if (m.input_tokens) updatedMsg.promptTokens = m.input_tokens;
            if (m.output_tokens) updatedMsg.completionTokens = m.output_tokens;
            // Only use actual_cost from OpenRouter, do not calculate or estimate
            if (m.actual_cost !== undefined) updatedMsg.cost = m.actual_cost;
            if (m.model_id) updatedMsg.modelName = m.model_id;
            if (m.generation_time_ms) updatedMsg.generationTimeMs = m.generation_time_ms;

            // Always track tokens, but only track cost if actual_cost is available
            const hasCost = m.actual_cost !== undefined;
            this.updateMetrics(
              m.total_tokens || 0,
              m.input_tokens || 0,
              m.output_tokens || 0,
              hasCost ? m.actual_cost : 0,
              m.tool_calls || 0,
              m.tool_errors || 0
            );
          }

          return updatedMsg;
        }));
      }

      // Mark as done streaming
      this.messages.update(msgs => msgs.map(m => {
        if (m.id === aiMsgId) {
          return { ...m, isStreaming: false };
        }
        return m;
      }));

      // If this was a new session, refresh the session list and ensure it's selected
      if (isNewSession) {
        await new Promise(resolve => setTimeout(resolve, 100)); // Brief delay for backend to persist
        this.chatService.listSessions().subscribe(sessions => {
          this.sessions.set(sessions);
          // Find and select the session we just created
          const currentSession = sessions.find(s => s.id === sessionId);
          if (currentSession) {
            this.sessions.update(s => s.map(session => ({
              ...session,
              active: session.id === sessionId
            })));
            console.log(`Session ${sessionId} created and selected with title: ${currentSession.title}`);
          }
        });
      }
    } catch (err) {
      // Check if this is an abort error (user cancelled)
      if (err instanceof Error && err.name === 'AbortError') {
        console.log('[AppComponent] Stream aborted by user');
        // Don't show error message for user-initiated cancellation
        // The stopAgent() method will handle updating the message
        this.messages.update(msgs => msgs.map(m => {
          if (m.id === aiMsgId) {
            return { ...m, isStreaming: false };
          }
          return m;
        }));
      } else {
        // Real error - show error message
        console.error('[AppComponent] Error in stream:', err);
        this.messages.update(msgs => msgs.map(m => {
          if (m.id === aiMsgId) {
            return {
              ...m,
              isStreaming: false,
              content: m.content + '\n\n⚠️ Error: ' + (err instanceof Error ? err.message : String(err))
            };
          }
          return m;
        }));
      }
    } finally {
      this.config.update(c => ({ ...c, status: 'idle' }));
    }
  }



  stopAgent() {
    const sessionId = this.currentSessionId();
    if (!sessionId) return;

    // 1. Abort the frontend stream immediately
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }

    this.config.update(c => ({ ...c, status: 'stopped' }));

    // 2. Notify backend to stop processing
    this.chatService.stopSession(sessionId).subscribe({
      next: () => {
        console.log('Agent stopped successfully');
        // Update the last message to show it was stopped
        this.messages.update(msgs => {
          const lastMsg = msgs[msgs.length - 1];
          if (lastMsg.role === 'assistant' && lastMsg.isStreaming) {
            return [
              ...msgs.slice(0, -1),
              { ...lastMsg, isStreaming: false, content: lastMsg.content + '\n\n[Stopped by user]' }
            ];
          }
          return msgs;
        });
      },
      error: (err) => console.error('Failed to stop agent:', err)
    });
  }
  updateMetrics(
    totalTokens: number,
    promptTokens: number,
    completionTokens: number,
    cost: number,
    toolCalls: number = 0,
    toolErrors: number = 0
  ) {
    this.metrics.update(m => ({
      totalTokens: m.totalTokens + totalTokens,
      promptTokens: m.promptTokens + promptTokens,
      completionTokens: m.completionTokens + completionTokens,
      sessionCost: m.sessionCost + cost,
      projectTotalCost: m.projectTotalCost + cost,
      toolCalls: m.toolCalls + toolCalls,
      toolErrors: m.toolErrors + toolErrors
    }));
  }

  updateConfigField(field: keyof AgentConfig, value: any) {
    this.config.update(c => ({ ...c, [field]: value }));
  }

  saveSettings() {
    localStorage.setItem('godoty_agent_config', JSON.stringify(this.config()));
    this.toggleSettings();
  }

  loadAgentConfig() {
    const saved = localStorage.getItem('godoty_agent_config');
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        // Ensure we don't overwrite status if it was 'working' (shouldn't be on reload but good practice)
        // Also reset showSettings to false
        this.config.update(c => ({
          ...c,
          ...parsed,
          status: 'idle',
          showSettings: false
        }));
      } catch (e) {
        console.error('Failed to load config', e);
      }
    }
  }

  loadSystemInfo() {
    this.desktopService.getSystemInfo().subscribe({
      next: (info) => console.log('System Info:', info),
      error: (err) => console.error('Failed to load system info', err)
    });

    // Also start monitoring Godot status
    this.desktopService.streamGodotStatus().subscribe(status => {
      this.updateGodotConfig(status);
    });
  }

  scrollToBottom() {
    if (this.scrollContainer) {
      try {
        this.scrollContainer.nativeElement.scrollTop = this.scrollContainer.nativeElement.scrollHeight;
      } catch (err) { }
    }
  }

  getGroupedEvents(msg: Message): GroupedEvent[] {
    if (msg.events && msg.events.length > 0) {
      const groupedEvents: GroupedEvent[] = [];
      let currentTextBlock: { content: string; sequence: number } | null = null;
      const toolMap = new Map<string, { toolCall: ToolCall; sequence: number }>();

      for (const event of msg.events) {
        if (event.type === 'text' && event.content) {
          // If we're already building a text block, append to it
          if (currentTextBlock) {
            currentTextBlock.content += event.content;
          } else {
            // Start a new text block
            currentTextBlock = {
              content: event.content,
              sequence: event.sequence
            };
          }
        } else if (event.type !== 'text') {
          // Non-text event encountered - flush current text block if exists
          if (currentTextBlock) {
            groupedEvents.push({
              type: 'text_block',
              content: currentTextBlock.content,
              sequence: currentTextBlock.sequence
            });
            currentTextBlock = null;
          }

          // Handle tool events - consolidate by tool name
          if (event.type === 'tool_use' || event.type === 'tool_result') {
            const toolName = event.toolCall?.name;
            if (toolName && event.toolCall) {
              // Update or add the tool in the map (always keeps the latest version)
              toolMap.set(toolName, {
                toolCall: event.toolCall,
                sequence: event.sequence
              });
            }
          }
        }
      }

      // Flush any remaining text block
      if (currentTextBlock) {
        groupedEvents.push({
          type: 'text_block',
          content: currentTextBlock.content,
          sequence: currentTextBlock.sequence
        });
      }

      // Add all tools from the map (deduplicated, with latest status)
      toolMap.forEach((tool) => {
        groupedEvents.push({
          type: 'tool',
          toolCall: tool.toolCall,
          sequence: tool.sequence
        });
      });

      // Sort by sequence to maintain chronological order
      groupedEvents.sort((a, b) => a.sequence - b.sequence);

      return groupedEvents;
    }

    // Fallback for messages without events array
    const events: GroupedEvent[] = [];
    if (msg.content) {
      events.push({ type: 'text_block', content: this.filterExecutionPlanBlocks(msg.content), sequence: 0 });
    }
    if (msg.toolCalls) {
      msg.toolCalls.forEach((tc, idx) => {
        events.push({ type: 'tool', toolCall: tc, sequence: idx + 1 });
      });
    }
    return events;
  }

  filterExecutionPlanBlocks(content: string): string {
    if (!content) return '';

    let filtered = content;

    // Remove <plan>...</plan> blocks
    filtered = filtered.replace(/<plan>[\s\S]*?<\/plan>/g, '');

    // Remove JSON execution plan blocks (common patterns)
    // Pattern 1: JSON objects with "steps" or "plan" keys
    filtered = filtered.replace(/\{[\s\S]*?"(?:steps|plan|execution_plan)"[\s\S]*?\}/g, '');

    // Pattern 2: Markdown code blocks containing JSON with plan/steps
    filtered = filtered.replace(/```(?:json)?\s*\{[\s\S]*?"(?:steps|plan|execution_plan)"[\s\S]*?\}\s*```/g, '');

    // Pattern 3: Remove any remaining empty code blocks
    filtered = filtered.replace(/```\s*```/g, '');

    // Clean up excessive whitespace that might result from filtering
    filtered = filtered.replace(/\n{3,}/g, '\n\n').trim();

    return filtered;
  }
}
