import React from 'react';
import { GraduationCap, Search } from 'lucide-react';

export const LoadingIndicator: React.FC = () => {
  return (
    <div
      className="animate-fade-in"
      style={{
        display: 'flex',
        justifyContent: 'flex-start',
        marginBottom: '24px',
        width: '100%',
      }}
    >
      <div style={{ display: 'flex', gap: '12px', maxWidth: '80%' }}>
        {/* Avatar Icon */}
        <div
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '50%',
            backgroundColor: '#0F766E',
            color: '#FFFFFF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            marginTop: '2px',
          }}
        >
          <GraduationCap size={20} />
        </div>

        {/* Loading Card */}
        <div
          style={{
            backgroundColor: '#FFFFFF',
            border: '1px solid #E2E8F0',
            borderRadius: '16px 16px 16px 4px',
            padding: '16px 20px',
            boxShadow: 'var(--card-shadow)',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <Search size={18} color="#0F766E" className="spin" />
          <div>
            <div style={{ fontSize: '0.9rem', fontWeight: 500, color: '#334155' }}>
              Searching university pages & analyzing faculty data...
            </div>
            <div style={{ fontSize: '0.75rem', color: '#94A3B8', marginTop: '2px' }}>
              Scraping websites with BeautifulSoup & Playwright engine
            </div>
          </div>

          <div style={{ display: 'flex', gap: '4px', marginLeft: '12px' }}>
            <span className="pulse-dot" style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#0F766E' }} />
            <span className="pulse-dot" style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#0F766E', animationDelay: '0.2s' }} />
            <span className="pulse-dot" style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#0F766E', animationDelay: '0.4s' }} />
          </div>
        </div>
      </div>
    </div>
  );
};
