import React from 'react';
import type { ChatMessage } from '../types';
import { ProfessorCard } from './ProfessorCard';
import { GraduationCap, User, AlertCircle } from 'lucide-react';

interface MessageBubbleProps {
  message: ChatMessage;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.sender === 'user';

  // Helper to render text with clean formatting (bold, URLs, bullet points, numbers)
  const renderFormattedText = (text: string) => {
    if (!text) return null;

    return text.split('\n').map((line, idx) => {
      const trimmed = line.trim();
      const isBullet = trimmed.startsWith('-') || trimmed.startsWith('*') || trimmed.startsWith('•');
      const numMatch = trimmed.match(/^(\d+)[\.\)]\s*(.*)$/);

      let cleanLine = line;
      let prefixEl: React.ReactNode = null;

      if (isBullet) {
        cleanLine = trimmed.replace(/^[\-\*\•]\s*/, '');
        prefixEl = <span style={{ color: '#0F766E', marginRight: '8px', fontWeight: 'bold' }}>•</span>;
      } else if (numMatch) {
        cleanLine = numMatch[2];
        prefixEl = (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '20px',
              height: '20px',
              borderRadius: '50%',
              backgroundColor: '#E0F2FE',
              color: '#0369A1',
              fontSize: '0.75rem',
              fontWeight: 700,
              marginRight: '8px',
              flexShrink: 0,
            }}
          >
            {numMatch[1]}
          </span>
        );
      }

      // Split by bold (**...**) and links (https?://...)
      const parts = cleanLine.split(/(\*\*.*?\*\*|https?:\/\/[^\s\)]+)/g);

      const formattedLine = parts.map((part, pIdx) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return (
            <strong key={pIdx} style={{ fontWeight: 600, color: isUser ? '#FFFFFF' : '#0F172A' }}>
              {part.slice(2, -2)}
            </strong>
          );
        }
        if (part.startsWith('http://') || part.startsWith('https://')) {
          return (
            <a
              key={pIdx}
              href={part}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: isUser ? '#67E8F9' : '#0284C7',
                textDecoration: 'underline',
                wordBreak: 'break-all',
              }}
            >
              {part}
            </a>
          );
        }
        return part;
      });

      return (
        <div
          key={idx}
          style={{
            marginBottom: trimmed === '' ? '8px' : '4px',
            paddingLeft: isBullet || numMatch ? '6px' : '0',
            display: isBullet || numMatch ? 'flex' : 'block',
            alignItems: 'flex-start',
          }}
        >
          {prefixEl}
          <div style={{ flex: 1 }}>{formattedLine}</div>
        </div>
      );
    });
  };

  return (
    <div
      className="animate-fade-in"
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: '24px',
        width: '100%',
      }}
    >
      <div
        style={{
          display: 'flex',
          gap: '12px',
          maxWidth: isUser ? '75%' : '90%',
          flexDirection: isUser ? 'row-reverse' : 'row',
        }}
      >
        {/* Avatar Icon */}
        <div
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '50%',
            backgroundColor: isUser ? '#1E293B' : '#0F766E',
            color: '#FFFFFF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            marginTop: '2px',
          }}
        >
          {isUser ? <User size={18} /> : <GraduationCap size={20} />}
        </div>

        {/* Bubble Content */}
        <div
          style={{
            backgroundColor: isUser ? '#1E293B' : message.isError ? '#FEF2F2' : '#FFFFFF',
            color: isUser ? '#FFFFFF' : '#0F172A',
            border: isUser
              ? 'none'
              : message.isError
              ? '1px solid #FCA5A5'
              : '1px solid #E2E8F0',
            borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
            padding: '16px 20px',
            boxShadow: isUser ? 'none' : 'var(--card-shadow)',
            width: '100%',
          }}
        >
          {/* Header Metadata */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: isUser ? '#94A3B8' : '#64748B' }}>
              {isUser ? 'You' : 'Scholarship Assistant'}
            </span>
            <span style={{ fontSize: '0.7rem', color: isUser ? '#64748B' : '#94A3B8' }}>
              {message.timestamp}
            </span>
          </div>

          {/* Error Message Case */}
          {message.isError ? (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', color: '#991B1B', fontSize: '0.9rem' }}>
              <AlertCircle size={18} style={{ marginTop: '2px', flexShrink: 0 }} />
              <div>{message.text}</div>
            </div>
          ) : message.professors && message.professors.length > 0 ? (
            /* Professors List Response Case */
            <div>
              {message.headerText && (
                <div style={{ fontSize: '0.95rem', color: '#334155', marginBottom: '16px', lineHeight: 1.5 }}>
                  {renderFormattedText(message.headerText)}
                </div>
              )}

              {/* Grid of Professor Cards */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
                  gap: '16px',
                  marginTop: '12px',
                  marginBottom: '12px',
                }}
              >
                {message.professors.map((prof) => (
                  <ProfessorCard key={prof.id} professor={prof} />
                ))}
              </div>

              {message.footerText && (
                <div style={{ fontSize: '0.9rem', color: '#64748B', marginTop: '16px', fontStyle: 'italic' }}>
                  {renderFormattedText(message.footerText)}
                </div>
              )}
            </div>
          ) : (
            /* Standard Text Response Case */
            <div style={{ fontSize: '0.95rem', lineHeight: 1.6 }}>
              {renderFormattedText(message.text)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
