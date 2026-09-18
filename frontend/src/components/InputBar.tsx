import React, { useState, useRef, useEffect } from 'react';
import { Send, Loader2, Compass } from 'lucide-react';

interface InputBarProps {
  onSendMessage: (message: string) => void;
  isLoading: boolean;
}

export const InputBar: React.FC<InputBarProps> = ({ onSendMessage, isLoading }) => {
  const [inputText, setInputText] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isLoading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isLoading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputText.trim() && !isLoading) {
      onSendMessage(inputText.trim());
      setInputText('');
    }
  };

  const handleChipClick = (prompt: string) => {
    if (!isLoading) {
      onSendMessage(prompt);
    }
  };

  const examplePrompts = [
    'KIU, Computer Science, Machine Learning, Assistant Professors',
    'NUST, Mechanical Engineering, Robotics, Professors',
    'Stanford, Computer Science, AI, All titles',
  ];

  return (
    <div
      style={{
        backgroundColor: '#FFFFFF',
        borderTop: '1px solid #E2E8F0',
        padding: '16px 24px',
        position: 'sticky',
        bottom: 0,
        boxShadow: '0 -2px 10px rgba(15, 23, 42, 0.03)',
      }}
    >
      <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
        {/* Example Quick Prompts */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', overflowX: 'auto', paddingBottom: '2px' }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748B', display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
            <Compass size={13} color="#0F766E" />
            Quick Examples:
          </span>
          {examplePrompts.map((prompt, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleChipClick(prompt)}
              disabled={isLoading}
              style={{
                fontSize: '0.75rem',
                color: '#334155',
                backgroundColor: '#F1F5F9',
                border: '1px solid #E2E8F0',
                borderRadius: '9999px',
                padding: '4px 12px',
                cursor: isLoading ? 'not-allowed' : 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                if (!isLoading) {
                  e.currentTarget.style.backgroundColor = '#E2E8F0';
                  e.currentTarget.style.borderColor = '#CBD5E1';
                }
              }}
              onMouseLeave={(e) => {
                if (!isLoading) {
                  e.currentTarget.style.backgroundColor = '#F1F5F9';
                  e.currentTarget.style.borderColor = '#E2E8F0';
                }
              }}
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
          <input
            ref={inputRef}
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Type university, department, research interests (e.g. KIU, CS, Machine Learning)..."
            disabled={isLoading}
            style={{
              flex: 1,
              padding: '14px 18px',
              fontSize: '0.95rem',
              color: '#0F172A',
              backgroundColor: isLoading ? '#F8FAFC' : '#FFFFFF',
              border: '1px solid #CBD5E1',
              borderRadius: '10px',
              outline: 'none',
              transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
              boxShadow: 'inset 0 1px 2px rgba(0, 0, 0, 0.03)',
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = '#0F766E';
              e.currentTarget.style.boxShadow = '0 0 0 3px rgba(15, 118, 110, 0.12)';
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = '#CBD5E1';
              e.currentTarget.style.boxShadow = 'inset 0 1px 2px rgba(0, 0, 0, 0.03)';
            }}
          />

          <button
            type="submit"
            disabled={!inputText.trim() || isLoading}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              padding: '14px 22px',
              fontSize: '0.9rem',
              fontWeight: 600,
              color: '#FFFFFF',
              backgroundColor: !inputText.trim() || isLoading ? '#94A3B8' : '#0F766E',
              border: 'none',
              borderRadius: '10px',
              cursor: !inputText.trim() || isLoading ? 'not-allowed' : 'pointer',
              transition: 'background-color 0.15s ease',
              boxShadow: '0 1px 2px rgba(0, 0, 0, 0.05)',
            }}
          >
            {isLoading ? (
              <>
                <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
                Scraping...
              </>
            ) : (
              <>
                Send
                <Send size={16} />
              </>
            )}
          </button>
        </form>

        {/* Footer Hint */}
        <div style={{ fontSize: '0.72rem', color: '#94A3B8', marginTop: '6px', textAlign: 'center' }}>
          Provide University Name, Department, Research Interests & Academic Titles for automatic search & scraping.
        </div>
      </div>
    </div>
  );
};
