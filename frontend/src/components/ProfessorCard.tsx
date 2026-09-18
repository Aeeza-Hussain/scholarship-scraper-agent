import React, { useState } from 'react';
import type { Professor } from '../types';
import { Mail, ExternalLink, Check, Copy, UserCheck, BookOpen } from 'lucide-react';

interface ProfessorCardProps {
  professor: Professor;
}

export const ProfessorCard: React.FC<ProfessorCardProps> = ({ professor }) => {
  const [copied, setCopied] = useState(false);

  const handleCopyEmail = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (professor.email && professor.email !== 'Not listed') {
      navigator.clipboard.writeText(professor.email);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const getTitleBadgeStyle = (title: string) => {
    const t = title.toLowerCase();
    if (t.includes('assistant')) {
      return { bg: '#F0FDF4', text: '#166534', border: '#DCFCE7', label: 'Assistant Professor' };
    }
    if (t.includes('associate')) {
      return { bg: '#EFF6FF', text: '#1E40AF', border: '#DBEAFE', label: 'Associate Professor' };
    }
    if (t.includes('lecturer') || t.includes('instructor')) {
      return { bg: '#FFF7ED', text: '#9A3412', border: '#FFEDD5', label: 'Lecturer / Teaching' };
    }
    return { bg: '#F5F3FF', text: '#5B21B6', border: '#DDD6FE', label: 'Full Professor' };
  };

  const badgeStyle = getTitleBadgeStyle(professor.title);

  return (
    <div
      style={{
        backgroundColor: '#FFFFFF',
        border: '1px solid #E2E8F0',
        borderRadius: '12px',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        boxShadow: 'var(--card-shadow)',
        transition: 'all 0.2s ease-in-out',
        position: 'relative',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = 'var(--card-shadow-hover)';
        e.currentTarget.style.borderColor = '#CBD5E1';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = 'var(--card-shadow)';
        e.currentTarget.style.borderColor = '#E2E8F0';
      }}
    >
      <div>
        {/* Top Header Row */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', marginBottom: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                backgroundColor: '#F1F5F9',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#0F766E',
                flexShrink: 0,
              }}
            >
              <UserCheck size={20} />
            </div>
            <div>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: '#0F172A', lineHeight: 1.3 }}>
                {professor.name}
              </h3>
            </div>
          </div>
        </div>

        {/* Title Badge */}
        <div style={{ marginBottom: '14px' }}>
          <span
            style={{
              display: 'inline-block',
              fontSize: '0.78rem',
              fontWeight: 600,
              padding: '3px 10px',
              borderRadius: '9999px',
              backgroundColor: badgeStyle.bg,
              color: badgeStyle.text,
              border: `1px solid ${badgeStyle.border}`,
            }}
          >
            {professor.title}
          </span>
        </div>

        {/* Research Interests */}
        <div style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.75rem', fontWeight: 600, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>
            <BookOpen size={13} color="#0F766E" />
            Research Areas
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
            {professor.research.map((item, idx) => (
              <span
                key={idx}
                style={{
                  fontSize: '0.8rem',
                  padding: '3px 9px',
                  borderRadius: '6px',
                  backgroundColor: '#F1F5F9',
                  color: '#334155',
                  border: '1px solid #E2E8F0',
                }}
              >
                {item}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Action Footer */}
      <div
        style={{
          borderTop: '1px solid #F1F5F9',
          paddingTop: '14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '10px',
          marginTop: 'auto',
        }}
      >
        {/* Email Link / Copy */}
        {professor.email && professor.email !== 'Not listed' ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <a
              href={`mailto:${professor.email}`}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '0.82rem',
                fontWeight: 500,
                color: '#0F766E',
                textDecoration: 'none',
                padding: '5px 10px',
                borderRadius: '6px',
                backgroundColor: '#F0FDF4',
                border: '1px solid #CCFBF1',
              }}
              title="Send outreach email"
            >
              <Mail size={14} />
              {professor.email}
            </a>
            <button
              onClick={handleCopyEmail}
              style={{
                background: 'none',
                border: '1px solid #E2E8F0',
                borderRadius: '6px',
                padding: '5px 8px',
                cursor: 'pointer',
                color: copied ? '#166534' : '#64748B',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
              title="Copy email address"
            >
              {copied ? <Check size={14} color="#166534" /> : <Copy size={14} />}
            </button>
          </div>
        ) : (
          <span style={{ fontSize: '0.82rem', color: '#94A3B8', fontStyle: 'italic' }}>
            Email: Not listed
          </span>
        )}

        {/* Profile URL */}
        {professor.profileUrl ? (
          <a
            href={professor.profileUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              fontSize: '0.82rem',
              fontWeight: 500,
              color: '#0284C7',
              textDecoration: 'none',
              padding: '5px 10px',
              borderRadius: '6px',
              backgroundColor: '#F0F9FF',
              border: '1px solid #E0F2FE',
            }}
          >
            Profile <ExternalLink size={13} />
          </a>
        ) : null}
      </div>
    </div>
  );
};
