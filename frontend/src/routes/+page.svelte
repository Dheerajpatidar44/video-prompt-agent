<script lang="ts">
  import { Send, Loader2, Play, CheckCircle2, User, Bot, Plus, MessageSquare, Menu, X, Trash2 } from '@lucide/svelte';
  import { ApiClient } from '$lib/api/client';
  import type { Question, Answer } from '$lib/types';
  import { tick, onMount } from 'svelte';

  // Chat state
  type MessageRole = 'user' | 'assistant';
  type MessageType = 'text' | 'questions' | 'results' | 'error';
  
  interface Message {
    id: string;
    role: MessageRole;
    content: string;
    type: MessageType;
    questions?: Question[];
    spec?: any;
    prompts?: any;
  }

  interface ChatSession {
    id: string;
    title: string;
    updatedAt: number;
    messages: Message[];
    pendingQuestions: Question[];
  }

  let messages = $state<Message[]>([]);
  let inputText = $state('');
  let selectedFile = $state<File | null>(null);
  let fileInput: HTMLInputElement;
  let isThinking = $state(false);
  let chatContainer: HTMLElement;
  let activeThreadId = $state<string | null>(null);
  let pendingQuestions = $state<Question[]>([]);
  
  // Sidebar & History State
  let chatHistory = $state<ChatSession[]>([]);
  let isSidebarOpen = $state(true);

  onMount(() => {
    // Load history on mount
    const saved = localStorage.getItem('vpa_chat_history');
    if (saved) {
      try {
        chatHistory = JSON.parse(saved);
        // Sort by newest first
        chatHistory.sort((a, b) => b.updatedAt - a.updatedAt);
      } catch (e) {
        console.error("Failed to parse chat history");
      }
    }
  });

  // Save current chat automatically whenever messages or state changes
  $effect(() => {
    if (activeThreadId && messages.length > 0) {
      const existingIdx = chatHistory.findIndex(c => c.id === activeThreadId);
      
      // Auto-generate title from the first user message
      let title = "New Video Script";
      const firstUserMsg = messages.find(m => m.role === 'user');
      if (firstUserMsg) {
        title = firstUserMsg.content.split('\n')[0].substring(0, 30).replace(/\[Attached File: .*\]/, '').trim() || title;
      }

      const session: ChatSession = {
        id: activeThreadId,
        title,
        updatedAt: Date.now(),
        messages: $state.snapshot(messages),
        pendingQuestions: $state.snapshot(pendingQuestions)
      };

      if (existingIdx >= 0) {
        chatHistory[existingIdx] = session;
      } else {
        chatHistory = [session, ...chatHistory];
      }
      
      localStorage.setItem('vpa_chat_history', JSON.stringify(chatHistory));
    }
  });

  function startNewChat() {
    activeThreadId = null;
    messages = [];
    pendingQuestions = [];
    inputText = '';
    selectedFile = null;
    if (window.innerWidth < 768) isSidebarOpen = false;
  }

  function loadChat(sessionId: string) {
    const session = chatHistory.find(c => c.id === sessionId);
    if (session) {
      activeThreadId = session.id;
      messages = session.messages;
      pendingQuestions = session.pendingQuestions;
      if (window.innerWidth < 768) isSidebarOpen = false;
      scrollToBottom();
    }
  }

  function deleteChat(sessionId: string, event: Event) {
    event.stopPropagation();
    chatHistory = chatHistory.filter(c => c.id !== sessionId);
    localStorage.setItem('vpa_chat_history', JSON.stringify(chatHistory));
    if (activeThreadId === sessionId) {
      startNewChat();
    }
  }

  // Auto-scroll
  async function scrollToBottom() {
    await tick();
    if (chatContainer) {
      chatContainer.scrollTop = chatContainer.scrollHeight;
    }
  }

  function addMessage(msg: Omit<Message, 'id'>) {
    messages = [...messages, { ...msg, id: Math.random().toString(36).substr(2, 9) }];
    scrollToBottom();
  }

  function handleFileChange(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      selectedFile = input.files[0];
    }
    input.value = '';
  }

  function removeFile() {
    selectedFile = null;
  }

  async function handleSubmit() {
    if ((!inputText.trim() && !selectedFile) || isThinking) return;

    const userText = inputText.trim();
    const currentFile = selectedFile;
    inputText = '';
    selectedFile = null;
    
    let content = userText;
    if (currentFile) {
      content = `[Attached File: ${currentFile.name}]\n${content}`;
    }

    addMessage({
      role: 'user',
      content: content.trim(),
      type: 'text'
    });

    isThinking = true;

    try {
      if (!activeThreadId) {
        await processInitialScript(userText, currentFile || undefined);
      } else if (pendingQuestions.length > 0) {
        await processAnswers(userText);
      } else {
        // If they type something after completion, maybe just reply saying it's done.
        addMessage({
          role: 'assistant',
          content: 'This video specification is already completed. Please start a New Chat to analyze a new script.',
          type: 'text'
        });
      }
    } catch (err: any) {
      addMessage({
        role: 'assistant',
        content: `Error: ${err.message || 'Something went wrong.'}`,
        type: 'error'
      });
    } finally {
      isThinking = false;
    }
  }

  async function processInitialScript(scriptContent: string, file?: File) {
    const response = await ApiClient.analyzeScript(file, scriptContent || undefined);
    activeThreadId = response.thread_id;
    await handleStatusRouting(response.status);
  }

  async function processAnswers(userText: string) {
    const answers: Answer[] = pendingQuestions.map(q => ({
      question_id: q.id,
      answer: userText,
      answer_type: q.answer_type || 'TEXT'
    }));
    pendingQuestions = [];
    const response = await ApiClient.submitAnswers(activeThreadId!, answers);
    await handleStatusRouting(response.status);
  }

  async function handleStatusRouting(status: string) {
    if (status === 'WAITING_FOR_USER') {
      const qRes = await ApiClient.getQuestions(activeThreadId!);
      pendingQuestions = qRes.questions;
      
      let content = "I need a few clarifications before generating the video prompts:\n\n";
      pendingQuestions.forEach((q, i) => {
        content += `${i + 1}. **${q.question}**\n`;
      });
      content += "\nPlease reply with your answers.";

      addMessage({ role: 'assistant', content, type: 'questions', questions: pendingQuestions });

    } else if (status === 'VALIDATING' || status === 'COMPLETED' || status === 'PLANNING' || status === 'GENERATING') {
      try {
        const specRes = await ApiClient.getSpecification(activeThreadId!);
        const promptsRes = await ApiClient.getPrompts(activeThreadId!);
        
        addMessage({
          role: 'assistant',
          content: 'I have finished analyzing your script and generating the video prompts. Here are the results:',
          type: 'results',
          spec: specRes.video_specification,
          prompts: promptsRes.prompt_set
        });
      } catch (e: any) {
        addMessage({
          role: 'assistant',
          content: `The process reached status ${status}, but fetching the final results failed: ${e.message}`,
          type: 'error'
        });
      }
    } else {
      addMessage({ role: 'assistant', content: `Agent reached a stopping point with status: ${status}.`, type: 'text' });
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }
</script>

<div class="flex h-screen w-full bg-[#343541] text-gray-100 font-sans overflow-hidden">
  
  <!-- Sidebar -->
  <div class="{isSidebarOpen ? 'translate-x-0' : '-translate-x-full'} fixed md:relative z-40 w-[260px] h-full bg-[#202123] flex-shrink-0 flex flex-col transition-transform duration-300 ease-in-out border-r border-gray-700/50">
    <div class="p-3 flex gap-2">
      <button 
        onclick={startNewChat}
        class="flex-1 flex items-center gap-3 border border-gray-600/50 rounded-md p-3 text-sm text-white hover:bg-[#2A2B32] transition-colors"
      >
        <Plus size={16} /> New Chat
      </button>
      <button 
        onclick={() => isSidebarOpen = false}
        class="md:hidden p-3 border border-gray-600/50 rounded-md text-gray-300 hover:text-white"
      >
        <X size={16} />
      </button>
    </div>
    
    <div class="flex-1 overflow-y-auto overflow-x-hidden p-3 space-y-1">
      <div class="text-xs font-semibold text-gray-500 mb-3 px-2 mt-2">Chat History</div>
      {#if chatHistory.length === 0}
        <div class="text-xs text-gray-500 px-2 italic">No previous chats</div>
      {/if}
      {#each chatHistory as chat}
         <button 
          onclick={() => loadChat(chat.id)} 
          class="group flex items-center gap-3 w-full p-3 rounded-md text-sm transition-colors {activeThreadId === chat.id ? 'bg-[#343541] text-white' : 'text-gray-300 hover:bg-[#2A2B32]'}"
         >
            <MessageSquare size={16} class="shrink-0" />
            <span class="truncate flex-1 text-left">{chat.title}</span>
            <div 
              role="button"
              tabindex="0"
              onclick={(e) => deleteChat(chat.id, e)}
              onkeydown={(e) => e.key === 'Enter' && deleteChat(chat.id, e)}
              class="opacity-0 group-hover:opacity-100 hover:text-red-400 transition-opacity p-1"
            >
              <Trash2 size={14} />
            </div>
         </button>
      {/each}
    </div>
    
    <div class="p-4 border-t border-gray-700/50 text-xs text-gray-500 flex items-center gap-2">
      <Bot size={14} /> Video Prompt Agent
    </div>
  </div>

  <!-- Mobile Overlay -->
  {#if isSidebarOpen}
    <div 
      class="fixed inset-0 bg-black/50 z-30 md:hidden"
      role="button"
      tabindex="0"
      onclick={() => isSidebarOpen = false}
      onkeydown={(e) => e.key === 'Enter' && (isSidebarOpen = false)}
    ></div>
  {/if}

  <!-- Main Chat Area -->
  <div class="flex-1 flex flex-col items-center w-full relative min-w-0">
    <!-- Header -->
    <header class="w-full h-14 border-b border-gray-700/50 flex items-center px-4 z-10 bg-[#343541]/90 backdrop-blur-sm sticky top-0 shrink-0">
      <button 
        onclick={() => isSidebarOpen = !isSidebarOpen}
        class="p-2 -ml-2 mr-2 text-gray-400 hover:text-white rounded-md hover:bg-gray-700/50 transition-colors"
      >
        <Menu size={20} />
      </button>
      <div class="flex items-center gap-2 text-gray-100 font-semibold">
        Video Prompt Agent
      </div>
    </header>

  <!-- Chat Area -->
  <div bind:this={chatContainer} class="flex-1 w-full overflow-y-auto px-4 pb-32 pt-8 scroll-smooth flex flex-col">
    {#if messages.length === 0}
      <div class="h-full flex flex-col items-center justify-center text-center opacity-70 mt-auto mb-auto">
        <div class="w-16 h-16 rounded-full bg-gray-800 flex items-center justify-center mb-6">
          <Play size={32} class="text-[#10a37f]" />
        </div>
        <h2 class="text-2xl font-semibold mb-2 text-white">How can I help you produce your video?</h2>
        <p class="text-gray-400 max-w-md">Paste your video script below and I'll analyze it for continuity, ask clarifying questions, and generate production-ready AI video prompts.</p>
      </div>
    {/if}

    <div class="flex flex-col w-full">
      {#each messages as msg (msg.id)}
        <div class="w-full py-6 {msg.role === 'assistant' ? 'bg-[#444654] border-y border-gray-700/50 -mx-4 px-4' : ''}">
          <div class="flex gap-4 max-w-3xl mx-auto">
            <div class="shrink-0 w-8 h-8 rounded flex items-center justify-center {msg.role === 'assistant' ? 'bg-[#10a37f]' : 'bg-[#5436DA]'}">
              {#if msg.role === 'assistant'}
                <Bot size={20} class="text-white" />
              {:else}
                <User size={20} class="text-white" />
              {/if}
            </div>
            <div class="flex-1 min-w-0 prose prose-invert max-w-none text-gray-100 leading-relaxed font-sans text-base">
              {#if msg.type === 'error'}
                <span class="text-red-400">{msg.content}</span>
              {:else}
                <div class="whitespace-pre-wrap">{msg.content}</div>
              {/if}

              {#if msg.type === 'results' && msg.prompts}
                <div class="mt-6 space-y-4">
                  <div class="p-4 rounded-xl bg-[#343541] border border-gray-700">
                    <h3 class="text-lg font-semibold mb-4 text-[#10a37f] flex items-center gap-2">
                      <CheckCircle2 size={20} />
                      Final Prompts ({msg.prompts.prompts?.length || 0})
                    </h3>
                    {#each msg.prompts.prompts || [] as p, i}
                      <div class="mb-4 pb-4 border-b border-gray-700/50 last:border-0 last:pb-0">
                        <div class="text-xs text-gray-400 mb-1 font-semibold tracking-wide uppercase">Shot {p.sequence_number} • {p.duration_seconds}s</div>
                        <div class="font-mono text-sm bg-black/40 p-3.5 rounded-lg text-gray-200 selection:bg-[#10a37f]/30 border border-gray-800">
                          {p.prompt_text}
                        </div>
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
            </div>
          </div>
        </div>
      {/each}

      {#if isThinking}
        <div class="w-full py-6 bg-[#444654] border-y border-gray-700/50 -mx-4 px-4">
          <div class="flex gap-4 max-w-3xl mx-auto">
            <div class="shrink-0 w-8 h-8 rounded bg-[#10a37f] flex items-center justify-center">
              <Bot size={20} class="text-white" />
            </div>
            <div class="flex-1 flex items-center gap-2 text-gray-300 font-sans">
              <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0ms"></span>
              <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 150ms"></span>
              <span class="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 300ms"></span>
            </div>
          </div>
        </div>
      {/if}
    </div>
  </div>

  <!-- Input Area -->
  <div class="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-[#343541] via-[#343541] to-transparent w-full">
    <div class="max-w-3xl mx-auto relative flex flex-col">
      <!-- File Preview Chip -->
      {#if selectedFile}
        <div class="mb-3 self-start flex items-center gap-2 bg-[#444654] border border-gray-600 rounded-lg px-3 py-2 shadow-md">
          <div class="bg-blue-600 p-1.5 rounded-md">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="text-white"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
          </div>
          <div class="flex flex-col max-w-[150px] overflow-hidden">
            <span class="text-sm font-medium text-gray-200 truncate">{selectedFile.name}</span>
            <span class="text-xs text-gray-400">{(selectedFile.size / 1024).toFixed(1)} KB</span>
          </div>
          <button onclick={removeFile} class="ml-2 text-gray-400 hover:text-white p-1 rounded-full hover:bg-gray-600 transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
      {/if}

      <div class="relative group flex items-end w-full">
        <input 
          type="file" 
          accept=".txt,.pdf" 
          bind:this={fileInput} 
          onchange={handleFileChange}
          class="hidden"
        />
        
        <button 
          onclick={() => fileInput.click()}
          disabled={isThinking || !!activeThreadId}
          class="absolute left-3 bottom-3 p-2 rounded-full text-gray-400 hover:text-white hover:bg-[#444654] transition-colors flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed z-10"
          title="Upload script file"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
        </button>

        <textarea
          bind:value={inputText}
          onkeydown={handleKeydown}
          disabled={isThinking}
          placeholder={messages.length === 0 ? "Paste script or click + to upload..." : "Reply to the agent..."}
          class="w-full bg-[#40414F] border border-gray-600 rounded-2xl py-4 pl-12 pr-12 text-white placeholder-gray-400 focus:outline-none focus:border-gray-500 focus:ring-1 focus:ring-gray-500 resize-none overflow-y-auto max-h-[200px] min-h-[56px] shadow-lg disabled:opacity-50 text-base"
          rows="1"
        ></textarea>
        
        <button 
          onclick={handleSubmit}
          disabled={isThinking || (!inputText.trim() && !selectedFile)}
          class="absolute right-3 bottom-3 p-2 rounded-lg bg-[#10a37f] hover:bg-[#1a886c] disabled:bg-gray-600 disabled:text-gray-400 text-white transition-colors flex items-center justify-center shadow-sm z-10"
        >
          <Send size={18} class="ml-0.5" />
        </button>
      </div>
    </div>
    <div class="text-center mt-2 text-xs text-gray-400">
      Video Prompt Agent can make mistakes. Verify important details.
    </div>
  </div>
  <!-- End Main Chat Area -->
</div>
</div>
