import { useState, useRef, useEffect } from 'react';
import { MessageCircle, Send, Brain } from 'lucide-react';
import { chatWithBundle } from '../api/client';
import DOMPurify from 'dompurify';
import type { ChatMessage } from '../types';

interface BundleChatProps {
  bundleId: string;
}

const SUGGESTED_QUESTIONS = [
  'What are the most critical issues?',
  'Why is the payment gateway crashing?',
  'Which pods are unhealthy?',
  "What's causing the 502 errors?",
];

function renderMarkdown(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Code blocks (triple backtick)
  html = html.replace(/```([\s\S]*?)```/g, (_match, code: string) => {
    return `<pre class="bg-navy-900 rounded p-2 my-1 text-xs font-mono overflow-x-auto">${code.trim()}</pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="bg-navy-900 px-1 py-0.5 rounded text-xs font-mono">$1</code>');

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-white">$1</strong>');

  // Bullet lists: lines starting with - or *
  html = html.replace(/^[\-\*]\s+(.+)$/gm, '<li class="ml-4 list-disc">$1</li>');
  // Wrap consecutive <li> in <ul>
  html = html.replace(/((?:<li[^>]*>.*<\/li>\n?)+)/g, '<ul class="my-1">$1</ul>');

  // Line breaks
  html = html.replace(/\n/g, '<br/>');

  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ['pre', 'code', 'strong', 'li', 'ul', 'br'],
    ALLOWED_ATTR: ['class'],
  });
}

export default function BundleChat({ bundleId }: BundleChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, loading]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const sendMessage = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    const userMessage: ChatMessage = { role: 'user', content: trimmed };
    const updatedHistory = [...messages, userMessage];
    setMessages(updatedHistory);
    setInput('');
    setError(null);
    setLoading(true);

    try {
      const response = await chatWithBundle(bundleId, {
        question: trimmed,
        history: messages,
      });
      const assistantMessage: ChatMessage = { role: 'assistant', content: response.answer, sources: response.sources };
      setMessages([...updatedHistory, assistantMessage]);
    } catch {
      setError('Failed to get a response. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="w-96 shrink-0 bg-navy-800 border-l border-navy-600 flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-navy-600 flex items-center gap-2">
        <div className="w-7 h-7 bg-accent-blue/20 rounded-lg flex items-center justify-center">
          <MessageCircle size={15} className="text-accent-blue" />
        </div>
        <h3 className="text-sm font-semibold text-white">Ask about this bundle</h3>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {isEmpty && !loading && (
          <div className="flex flex-col items-center justify-center h-full gap-4 text-center">
            <div className="w-12 h-12 bg-accent-purple/20 rounded-xl flex items-center justify-center">
              <Brain size={24} className="text-accent-purple" />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-300 mb-1">Ask about this bundle</p>
              <p className="text-xs text-gray-500">AI-powered insights scoped to this bundle's issues, logs, and cluster health</p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center mt-2">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="text-xs bg-navy-700 border border-navy-600 text-gray-300 px-3 py-1.5 rounded-full hover:bg-navy-600 hover:text-white transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={`${msg.role}-${idx}`} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                msg.role === 'user'
                  ? 'bg-accent-blue/20 text-gray-200 rounded-br-sm'
                  : 'bg-navy-700 text-gray-300 rounded-bl-sm'
              }`}
            >
              {msg.role === 'assistant' ? (
                <>
                  <div
                    className="leading-relaxed [&_pre]:my-1 [&_ul]:my-1 [&_li]:text-gray-300"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                  />
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-navy-600">
                      <p className="text-[10px] text-gray-500 mb-1">Sources:</p>
                      <div className="flex flex-wrap gap-1">
                        {msg.sources.filter(s => s.startsWith('[RAG')).slice(0, 4).map((s, i) => (
                          <span key={i} className="text-[9px] bg-navy-800 border border-navy-600 rounded px-1.5 py-0.5 text-gray-500">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <p className="leading-relaxed whitespace-pre-line">{msg.content}</p>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start" role="status" aria-label="Assistant is typing">
            <div className="bg-navy-700 rounded-xl rounded-bl-sm px-4 py-3">
              <div className="flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="flex justify-start" aria-live="polite">
            <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2 text-sm text-red-400">
              {error}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-navy-600">
        <div className="flex items-center gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this bundle's cluster data..."
            disabled={loading}
            className="flex-1 bg-navy-700 border border-navy-600 rounded-lg px-3 py-2 text-sm text-gray-300 outline-none focus:border-accent-blue placeholder-gray-500 disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || loading}
            aria-label="Send message"
            className="w-8 h-8 bg-accent-blue hover:bg-blue-600 disabled:bg-navy-600 disabled:text-gray-500 text-white rounded-lg flex items-center justify-center transition-colors shrink-0"
          >
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
