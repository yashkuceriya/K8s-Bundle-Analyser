import { useState, useRef, useEffect } from 'react';
import { Send, Bot, ChevronDown, ChevronRight, FolderOpen, Plus } from 'lucide-react';
import { chatWithBundle } from '../api/client';
import DOMPurify from 'dompurify';
import type { ChatMessage } from '../types';

interface BundleChatProps {
  bundleId: string;
}

const SUGGESTED_QUESTIONS = [
  'Show pod yaml',
  'Analyze network policy',
  'Recent config changes',
  'What are the most critical issues?',
];

// Keep the existing renderMarkdown function exactly as-is
function renderMarkdown(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  html = html.replace(/```([\s\S]*?)```/g, (_match, code: string) => {
    return `<pre class="bg-navy-900 rounded p-2 my-1 text-xs font-mono overflow-x-auto">${code.trim()}</pre>`;
  });
  html = html.replace(/`([^`]+)`/g, '<code class="bg-navy-900 px-1 py-0.5 rounded text-xs font-mono text-accent-blue">$1</code>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold text-white">$1</strong>');
  html = html.replace(/^[\-\*]\s+(.+)$/gm, '<li class="ml-4 list-disc">$1</li>');
  html = html.replace(/((?:<li[^>]*>.*<\/li>\n?)+)/g, '<ul class="my-1">$1</ul>');
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
  const [expandedSources, setExpandedSources] = useState<Set<number>>(new Set());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, loading]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Keep the exact same sendMessage function
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

  const toggleSources = (idx: number) => {
    setExpandedSources(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const shortId = bundleId.slice(0, 8).toUpperCase();

  return (
    <div className="flex flex-col h-full bg-navy-800 rounded-xl border border-navy-700 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-navy-700 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-navy-700 rounded-lg flex items-center justify-center">
            <Bot size={18} className="text-gray-400" />
          </div>
          <h3 className="text-sm font-semibold text-white">Bundle Intelligence Assistant</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-accent-green" />
          <span className="text-xs text-gray-400 font-mono">CONTEXT: {shortId}</span>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {messages.length === 0 && !loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 bg-navy-700 rounded-lg flex items-center justify-center shrink-0 mt-1">
              <Bot size={16} className="text-gray-400" />
            </div>
            <div className="bg-navy-700/50 rounded-xl rounded-tl-sm px-4 py-3 max-w-[80%]">
              <p className="text-sm text-gray-300 leading-relaxed">
                Hello! I've analyzed the <code className="text-accent-blue bg-navy-900 px-1 rounded text-xs">{shortId}</code> diagnostics.
                How can I help you investigate?
              </p>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <div key={`${msg.role}-${idx}`}>
            {msg.role === 'assistant' ? (
              <div className="flex gap-3">
                <div className="w-8 h-8 bg-navy-700 rounded-lg flex items-center justify-center shrink-0 mt-1">
                  <Bot size={16} className="text-gray-400" />
                </div>
                <div className="max-w-[80%] space-y-2">
                  <div className="text-sm text-gray-300 leading-relaxed">
                    <div
                      className="[&_pre]:my-1 [&_ul]:my-1 [&_li]:text-gray-300 [&_code]:text-accent-blue"
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
                    />
                  </div>
                  {/* Sources */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="bg-navy-900/50 border border-navy-700 rounded-lg overflow-hidden">
                      <button
                        onClick={() => toggleSources(idx)}
                        className="w-full flex items-center gap-2 px-3 py-2 text-xs text-gray-400 hover:text-gray-300 transition-colors"
                      >
                        <FolderOpen size={14} />
                        <span className="font-semibold uppercase tracking-wider">Sources ({msg.sources.length} events found)</span>
                        {expandedSources.has(idx) ? <ChevronDown size={14} className="ml-auto" /> : <ChevronRight size={14} className="ml-auto" />}
                      </button>
                      {expandedSources.has(idx) && (
                        <div className="border-t border-navy-700 px-3 py-2 space-y-1.5">
                          {msg.sources.slice(0, 6).map((s, si) => {
                            const level = s.includes('ERROR') || s.includes('error') ? 'ERROR' :
                                          s.includes('WARN') || s.includes('warn') ? 'WARN' :
                                          s.includes('DEBUG') || s.includes('debug') ? 'DEBUG' : 'INFO';
                            const levelColor = level === 'ERROR' ? 'text-red-400' :
                                              level === 'WARN' ? 'text-amber-400' :
                                              level === 'DEBUG' ? 'text-gray-500' : 'text-accent-blue';
                            return (
                              <div key={si} className="flex items-start gap-3 text-xs font-mono py-1">
                                <span className={`${levelColor} font-semibold w-12 shrink-0`}>{level}</span>
                                <span className="text-gray-500 truncate">{s}</span>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex justify-end">
                <div className="max-w-[80%] bg-accent-blue/20 border border-accent-blue/30 rounded-xl rounded-br-sm px-4 py-2.5">
                  <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-line">{msg.content}</p>
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-3" role="status" aria-label="Assistant is typing">
            <div className="w-8 h-8 bg-navy-700 rounded-lg flex items-center justify-center shrink-0">
              <Bot size={16} className="text-gray-400" />
            </div>
            <div className="bg-navy-700/50 rounded-xl rounded-tl-sm px-4 py-3">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="flex justify-start" aria-live="polite">
            <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-3 py-2 text-sm text-red-400 ml-11">
              {error}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggestion Chips */}
      <div className="px-5 py-2 flex flex-wrap gap-2">
        {SUGGESTED_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => sendMessage(q)}
            disabled={loading}
            className="text-xs bg-navy-700 border border-navy-600 text-gray-300 px-3 py-1.5 rounded-full hover:bg-navy-600 hover:text-white transition-colors disabled:opacity-50"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input */}
      <div className="px-5 py-3 border-t border-navy-700">
        <div className="flex items-center gap-3 bg-navy-900 border border-navy-700 rounded-xl px-4 py-2.5">
          <button className="text-gray-500 hover:text-gray-300 transition-colors shrink-0">
            <Plus size={18} />
          </button>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this bundle..."
            disabled={loading}
            className="flex-1 bg-transparent text-sm text-gray-300 outline-none placeholder-gray-600 disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || loading}
            aria-label="Send message"
            className="w-8 h-8 bg-accent-blue hover:bg-blue-600 disabled:bg-navy-700 disabled:text-gray-600 text-white rounded-lg flex items-center justify-center transition-colors shrink-0"
          >
            <Send size={14} />
          </button>
        </div>
        <p className="text-[10px] text-gray-600 text-center mt-2">
          Intelligence Assistant can make mistakes. Verify critical infrastructure changes.
        </p>
      </div>
    </div>
  );
}
