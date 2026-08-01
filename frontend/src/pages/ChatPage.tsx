import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, streamChatQuery } from '../services/api';
import { useApp } from '../context/AppContext';
import { ChatSession, ChatMessage, Citation } from '../types';
import {
  Send,
  Plus,
  MessageSquare,
  FileText,
  Bookmark,
  Sparkles,
  ExternalLink,
  ChevronRight,
  ShieldCheck,
  Bot,
  User as UserIcon,
  X
} from 'lucide-react';

export const ChatPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const scopedDocId = searchParams.get('doc');

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputQuery, setInputQuery] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const { documents: allDocuments, fetchDocuments } = useApp();
  const indexedDocuments = allDocuments.filter((d) => d.status === 'indexed');
  const [selectedDocFilter, setSelectedDocFilter] = useState<string[]>([]);
  const [previewCitation, setPreviewCitation] = useState<Citation | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load chat sessions and available documents
  useEffect(() => {
    fetchSessions();
    fetchDocuments();
  }, [fetchDocuments]);

  useEffect(() => {
    if (scopedDocId) {
      setSelectedDocFilter([scopedDocId]);
    }
  }, [scopedDocId]);

  useEffect(() => {
    if (activeSessionId) {
      loadMessages(activeSessionId);
    }
  }, [activeSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const fetchSessions = async () => {
    try {
      const res = await api.get('/chat/sessions');
      setSessions(res.data);
      if (res.data.length > 0 && !activeSessionId) {
        setActiveSessionId(res.data[0].id);
      } else if (res.data.length === 0) {
        createNewSession();
      }
    } catch (err) {
      console.error('Failed to fetch chat sessions', err);
    }
  };



  const createNewSession = async () => {
    try {
      const res = await api.post('/chat/sessions', {
        title: 'New RAG Session',
        document_ids: selectedDocFilter,
      });
      setSessions((prev) => [res.data, ...prev]);
      setActiveSessionId(res.data.id);
      setMessages([]);
    } catch (err) {
      console.error('Failed to create session', err);
    }
  };

  const loadMessages = async (sessionId: string) => {
    try {
      const res = await api.get(`/chat/sessions/${sessionId}/messages`);
      setMessages(res.data);
    } catch (err) {
      console.error('Failed to load messages', err);
    }
  };

  const handleSend = () => {
    if (!inputQuery.trim() || !activeSessionId || isStreaming) return;

    const userText = inputQuery.trim();
    setInputQuery('');

    // Append user message immediately
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      sender: 'user',
      text: userText,
      created_at: new Date().toISOString(),
    };

    // Prepare assistant placeholder message
    const assistantMsgId = (Date.now() + 1).toString();
    const assistantMsg: ChatMessage = {
      id: assistantMsgId,
      sender: 'assistant',
      text: '',
      citations: [],
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    streamChatQuery(
      activeSessionId,
      userText,
      selectedDocFilter.length > 0 ? selectedDocFilter : undefined,
      (token: string) => {
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantMsgId ? { ...msg, text: msg.text + token } : msg))
        );
      },
      (citations: Citation[]) => {
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantMsgId ? { ...msg, citations } : msg))
        );
      },
      () => {
        setIsStreaming(false);
      },
      (err: any) => {
        console.error('Streaming error', err);
        setIsStreaming(false);
      }
    );
  };

  return (
    <div className="h-[calc(100vh-4rem)] flex overflow-hidden bg-slate-950">
      {/* Pane 1: Left Session & Scope Sidebar */}
      <div className="w-80 bg-slate-900 border-r border-slate-800 flex flex-col justify-between hidden lg:flex">
        <div className="p-4 space-y-4 overflow-y-auto">
          <button
            onClick={createNewSession}
            className="w-full py-2.5 px-4 bg-brand-600 hover:bg-brand-500 text-white font-semibold rounded-xl text-xs shadow-soft-sm flex items-center justify-center gap-2 transition"
          >
            <Plus className="w-4 h-4" /> New RAG Conversation
          </button>

          {/* Document Scope Filter */}
          <div className="space-y-2 border-t border-slate-800 pt-3">
            <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block">
              Document Scope
            </label>
            <select
              value={selectedDocFilter[0] || 'all'}
              onChange={(e) =>
                setSelectedDocFilter(e.target.value === 'all' ? [] : [e.target.value])
              }
              className="w-full p-2.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 focus:outline-none focus:border-brand-500"
            >
              <option value="all">All Indexed Documents ({indexedDocuments.length})</option>
              {indexedDocuments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename}
                </option>
              ))}
            </select>
          </div>

          {/* Chat Sessions History */}
          <div className="space-y-1 border-t border-slate-800 pt-3">
            <label className="text-xs font-bold text-slate-400 uppercase tracking-wider block mb-2">
              Recent Chat Sessions
            </label>
            {sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => setActiveSessionId(s.id)}
                className={`w-full text-left px-3 py-2.5 rounded-xl text-xs font-medium truncate flex items-center gap-2 transition ${
                  s.id === activeSessionId
                    ? 'bg-brand-600/30 text-brand-300 border border-brand-500/40'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`}
              >
                <MessageSquare className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{s.title}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="p-3 border-t border-slate-800 bg-slate-900/50 text-[11px] text-slate-500 flex items-center gap-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-brand-400" />
          <span>Strict low-confidence grounding active</span>
        </div>
      </div>

      {/* Pane 2: Main RAG Chat Conversation Panel */}
      <div className="flex-1 flex flex-col justify-between bg-slate-950 relative">
        {/* Chat Messages View */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-6">
              <div className="w-16 h-16 rounded-2xl bg-brand-600/20 text-brand-400 flex items-center justify-center mb-4">
                <Sparkles className="w-8 h-8" />
              </div>
              <h2 className="text-xl font-bold text-white">Ask your Grounded Document Assistant</h2>
              <p className="text-xs text-slate-400 max-w-md mt-2">
                Ask questions about your uploaded PDFs and scans. Answers are generated strictly from indexed chunks with exact citations.
              </p>
              <div className="mt-6 flex flex-wrap gap-2 justify-center">
                <button
                  onClick={() => setInputQuery('Summarize the key findings from the uploaded document.')}
                  className="px-3 py-1.5 bg-slate-900 border border-slate-800 hover:border-brand-500 rounded-xl text-xs text-slate-300 transition"
                >
                  "Summarize key findings"
                </button>
                <button
                  onClick={() => setInputQuery('What are the key topics discussed in the document?')}
                  className="px-3 py-1.5 bg-slate-900 border border-slate-800 hover:border-brand-500 rounded-xl text-xs text-slate-300 transition"
                >
                  "Key topics overview"
                </button>
              </div>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-4 max-w-3xl ${
                  msg.sender === 'user' ? 'ml-auto flex-row-reverse' : 'mr-auto'
                }`}
              >
                <div
                  className={`w-9 h-9 rounded-xl flex items-center justify-center text-white shrink-0 ${
                    msg.sender === 'user'
                      ? 'bg-brand-600'
                      : 'bg-gradient-to-tr from-indigo-500 to-purple-500'
                  }`}
                >
                  {msg.sender === 'user' ? <UserIcon className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                </div>

                <div className="space-y-2 max-w-2xl">
                  <div
                    className={`p-4 rounded-2xl text-sm leading-relaxed ${
                      msg.sender === 'user'
                        ? 'bg-brand-600 text-white rounded-tr-none'
                        : 'bg-slate-900 text-slate-100 border border-slate-800 rounded-tl-none'
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.text || (isStreaming ? 'Thinking...' : '')}</p>
                  </div>

                  {/* Citations list */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider w-full">
                        Source Citations:
                      </span>
                      {msg.citations.map((cite, idx) => (
                        <button
                          key={idx}
                          onClick={() => setPreviewCitation(cite)}
                          className="px-2.5 py-1 bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-brand-500/50 rounded-lg text-xs text-brand-300 flex items-center gap-1.5 transition"
                        >
                          <Bookmark className="w-3 h-3 text-brand-400" />
                          <span>
                            {cite.document_name} (Page {cite.page_number})
                          </span>
                          <ExternalLink className="w-3 h-3 text-slate-500" />
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/60 backdrop-blur-md">
          <div className="max-w-4xl mx-auto flex items-center gap-2 bg-slate-950 border border-slate-800 focus-within:border-brand-500 rounded-2xl p-2 transition">
            <input
              type="text"
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="Ask a question about your indexed documents..."
              className="flex-1 bg-transparent px-3 py-2 text-sm text-white focus:outline-none"
            />

            <button
              onClick={handleSend}
              disabled={isStreaming || !inputQuery.trim()}
              className="p-2.5 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white rounded-xl transition"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Pane 3: Right Document & Citation Preview Panel */}
      {previewCitation && (
        <div className="w-96 bg-slate-900 border-l border-slate-800 p-6 flex flex-col justify-between hidden xl:flex">
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="font-bold text-sm text-white flex items-center gap-2">
                <FileText className="w-4 h-4 text-brand-400" /> Citation Preview
              </h3>
              <button
                onClick={() => setPreviewCitation(null)}
                className="text-slate-400 hover:text-white p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2">
              <span className="text-xs font-semibold text-brand-400">
                Document: {previewCitation.document_name}
              </span>
              <p className="text-xs text-slate-400">Page Number: {previewCitation.page_number}</p>
            </div>

            <div className="p-4 bg-slate-950 rounded-xl border border-slate-800 space-y-2">
              <span className="text-[11px] font-bold text-slate-500 uppercase">Retrieved Chunk Context</span>
              <p className="text-xs text-slate-200 leading-relaxed italic">
                "{previewCitation.snippet}"
              </p>
            </div>
          </div>

          <div className="p-3 bg-brand-950/40 border border-brand-800/40 rounded-xl text-xs text-brand-300">
            Grounding Verified: Chunk retrieved via hybrid vector search (RRF).
          </div>
        </div>
      )}
    </div>
  );
};
