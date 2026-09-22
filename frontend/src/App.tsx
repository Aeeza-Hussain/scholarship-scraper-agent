import React, { useState, useEffect, useRef } from 'react';
import { Header } from './components/Header';
import { MessageBubble } from './components/MessageBubble';
import { InputBar } from './components/InputBar';
import { LoadingIndicator } from './components/LoadingIndicator';
import type { ChatMessage, SessionData } from './types';
import { parseProfessorResponse } from './utils/parser';

// Resilient API caller: Uses Vite dev proxy (/api) to eliminate CORS and network issues,
// with automatic fallback to direct backend host (http://127.0.0.1:8001).
const apiFetch = async (path: string, options?: RequestInit): Promise<Response> => {
  try {
    const res = await fetch(path, options);
    // If the proxy handled it or returned a valid HTTP response
    if (res.status > 0) return res;
  } catch {
    // Relative fetch failed, fall through to direct backend URL
  }
  return fetch(`http://127.0.0.1:8001${path}`, options);
};

export const App: React.FC = () => {
  const [session, setSession] = useState<SessionData | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [modelName, setModelName] = useState<string>('gemini-2.5-flash');

  const chatContainerRef = useRef<HTMLDivElement>(null);

  // Auto scroll chat to bottom when messages update
  useEffect(() => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  // Create new session on mount
  useEffect(() => {
    initNewSession();
  }, []);

  const initNewSession = async () => {
    setIsInitializing(true);
    setIsLoading(true);
    setErrorMsg(null);

    // Fetch active model from health check
    apiFetch('/api/health')
      .then((res) => res.json())
      .then((data) => {
        if (data.model) setModelName(data.model);
      })
      .catch(() => {});

    try {
      const res = await apiFetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (!res.ok) {
        throw new Error(`Session creation failed (HTTP ${res.status})`);
      }

      const data: SessionData = await res.json();
      setSession(data);

      const parsedGreeting = parseProfessorResponse(data.greeting);

      const initialMessage: ChatMessage = {
        id: `msg-0-${Date.now()}`,
        sender: 'assistant',
        text: data.greeting,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        professors: parsedGreeting.professors,
        headerText: parsedGreeting.headerText,
        footerText: parsedGreeting.footerText,
      };

      setMessages([initialMessage]);
    } catch (err: any) {
      console.error('Session initialization error:', err);
      setErrorMsg(
        'Unable to connect to FastAPI backend at http://127.0.0.1:8001. Ensure the backend server is running.'
      );
    } finally {
      setIsInitializing(false);
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (userText: string) => {
    if (!userText.trim() || isLoading) return;

    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: userText,
      timestamp,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);
    setErrorMsg(null);

    try {
      const payload = {
        message: userText,
        user_id: session?.user_id || 'user_default',
        session_id: session?.session_id || '',
      };

      const res = await apiFetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || `Chat request failed (HTTP ${res.status})`);
      }

      const data = await res.json();
      const replyText = data.reply || 'No response returned.';

      // Update active session IDs if updated by server
      if (data.session_id && data.user_id) {
        setSession((prev) =>
          prev
            ? { ...prev, session_id: data.session_id, user_id: data.user_id }
            : { session_id: data.session_id, user_id: data.user_id, greeting: '' }
        );
      }

      if (data.active_model) {
        setModelName(data.active_model);
      }

      // Parse response text for professor card listings
      const parsed = parseProfessorResponse(replyText);

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        sender: 'assistant',
        text: replyText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        professors: parsed.professors,
        headerText: parsed.headerText,
        footerText: parsed.footerText,
        toolCallsCount: data.tool_calls_this_turn,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: any) {
      console.error('Chat API Error:', err);

      const errorMessage: ChatMessage = {
        id: `err-${Date.now()}`,
        sender: 'assistant',
        text: err.message || 'An error occurred while connecting to the scraper backend.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        isError: true,
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        backgroundColor: 'var(--bg-main)',
      }}
    >
      {/* Top Academic Header */}
      <Header onNewSearch={initNewSession} isInitializing={isInitializing} modelName={modelName} />

      {/* Main Conversation Container */}
      <main
        ref={chatContainerRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '24px 16px',
        }}
      >
        <div
          style={{
            maxWidth: '1000px',
            margin: '0 auto',
          }}
        >
          {/* Global Backend Error Banner */}
          {errorMsg && (
            <div
              style={{
                backgroundColor: '#FEF2F2',
                border: '1px solid #FECACA',
                color: '#991B1B',
                padding: '16px 20px',
                borderRadius: '12px',
                marginBottom: '24px',
                fontSize: '0.9rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div>
                <strong>Connection Warning:</strong> {errorMsg}
              </div>
              <button
                onClick={initNewSession}
                style={{
                  backgroundColor: '#991B1B',
                  color: '#FFFFFF',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '6px 12px',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Retry
              </button>
            </div>
          )}

          {/* Chat Messages List */}
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* Loading Indicator while agent searches/scrapes */}
          {isLoading && !isInitializing && <LoadingIndicator />}
        </div>
      </main>

      {/* Input Bar at Bottom */}
      <InputBar onSendMessage={handleSendMessage} isLoading={isLoading || isInitializing} />
    </div>
  );
};

export default App;
