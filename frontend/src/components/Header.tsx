import React from 'react';
import { GraduationCap, RotateCcw, Sparkles } from 'lucide-react';

interface HeaderProps {
  onNewSearch: () => void;
  isInitializing: boolean;
  modelName?: string;
}

export const Header: React.FC<HeaderProps> = ({ onNewSearch, isInitializing, modelName = 'gemini-3.6-flash' }) => {
  return (
    <header
      style={{
        backgroundColor: '#FFFFFF',
        borderBottom: '1px solid #E2E8F0',
        padding: '16px 24px',
        position: 'sticky',
        top: 0,
        zIndex: 10,
        boxShadow: '0 1px 2px 0 rgba(15, 23, 42, 0.03)',
      }}
    >
      <div
        style={{
          maxWidth: '1200px',
          margin: '0 auto',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        {/* Brand & Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div
            style={{
              width: '42px',
              height: '42px',
              borderRadius: '10px',
              backgroundColor: '#0F766E',
              color: '#FFFFFF',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 2px 4px rgba(15, 118, 110, 0.25)',
            }}
          >
            <GraduationCap size={24} />
          </div>
          <div>
            <h1 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0F172A', letterSpacing: '-0.01em', lineHeight: 1.2 }}>
              Scholarship Professor Finder
            </h1>
            <p style={{ fontSize: '0.8rem', color: '#64748B', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Sparkles size={12} color="#0F766E" />
              Academic Outreach & Faculty Discovery Agent
            </p>
          </div>
        </div>

        {/* Status Badge & Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Active Model Indicator */}
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '0.75rem',
              fontWeight: 500,
              padding: '4px 10px',
              borderRadius: '9999px',
              backgroundColor: '#F1F5F9',
              color: '#334155',
              border: '1px solid #E2E8F0',
            }}
          >
            <span
              style={{
                width: '7px',
                height: '7px',
                borderRadius: '50%',
                backgroundColor: '#10B981',
                display: 'inline-block',
              }}
            />
            {modelName}
          </div>

          {/* New Search Button */}
          <button
            onClick={onNewSearch}
            disabled={isInitializing}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              fontSize: '0.85rem',
              fontWeight: 600,
              color: '#0F766E',
              backgroundColor: '#F0FDF4',
              border: '1px solid #99F6E4',
              borderRadius: '8px',
              padding: '8px 14px',
              cursor: isInitializing ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s ease',
              opacity: isInitializing ? 0.6 : 1,
            }}
            onMouseEnter={(e) => {
              if (!isInitializing) e.currentTarget.style.backgroundColor = '#CCFBF1';
            }}
            onMouseLeave={(e) => {
              if (!isInitializing) e.currentTarget.style.backgroundColor = '#F0FDF4';
            }}
          >
            <RotateCcw size={15} className={isInitializing ? 'spin' : ''} />
            New Search
          </button>
        </div>
      </div>
    </header>
  );
};
