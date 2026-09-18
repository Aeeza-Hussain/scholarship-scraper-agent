import type { Professor } from '../types';

/**
 * Parses raw text from the agent response to extract structured professor card data
 * if the response contains matching faculty listings.
 */
export function parseProfessorResponse(text: string): {
  headerText: string;
  professors: Professor[];
  footerText: string;
} {
  if (!text) return { headerText: '', professors: [], footerText: '' };

  const lines = text.split('\n');
  const professors: Professor[] = [];
  const headerLines: string[] = [];
  const footerLines: string[] = [];

  let currentProf: Partial<Professor> | null = null;
  let inProfSection = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Match professor header line: "1. **Dr. Ali Khan** — Assistant Professor" or "1. **Sara Achour** - Assistant Professor"
    const profHeaderMatch = trimmed.match(/^\d+[\.\)]\s*(?:\*\*)?(.*?)(?:\*\*)?\s*[\—\–\-]\s*(.*)$/);

    if (profHeaderMatch) {
      inProfSection = true;
      if (currentProf && currentProf.name) {
        professors.push(finalizeProf(currentProf, professors.length));
      }

      let rawName = profHeaderMatch[1].replace(/\*\*/g, '').trim();
      let rawTitle = profHeaderMatch[2].replace(/\*\*/g, '').trim();

      // Clean up markdown bolds
      rawName = rawName.replace(/^[\s\*]+|[\s\*]+$/g, '');

      currentProf = {
        name: rawName,
        title: rawTitle || 'Faculty Member',
        research: [],
        email: '',
        profileUrl: '',
      };
      continue;
    }

    if (inProfSection && currentProf) {
      // Research line parsing
      if (trimmed.toLowerCase().includes('research:') || trimmed.includes('🔬')) {
        const match = trimmed.match(/(?:research:\s*|\🔬\s*\*\*research:\*\*\s*)(.*)/i);
        if (match && match[1]) {
          const rawResearch = match[1].replace(/\*\*/g, '').trim();
          const items = rawResearch
            .split(/[,;]/)
            .map((s) => s.trim())
            .filter((s) => s.length > 0 && s.toLowerCase() !== 'not listed');
          currentProf.research = items.length > 0 ? items : ['General Research'];
        }
        continue;
      }

      // Email line parsing
      if (trimmed.toLowerCase().includes('email:') || trimmed.includes('📧')) {
        const match = trimmed.match(/(?:email:\s*|\📧\s*\*\*email:\*\*\s*)([^\s\)]+)/i);
        if (match && match[1]) {
          let cleanEmail = match[1].replace(/[\[\]\(\)]/g, '').trim();
          if (cleanEmail.toLowerCase() !== 'not listed' && cleanEmail.includes('@')) {
            currentProf.email = cleanEmail;
          } else {
            currentProf.email = 'Not listed';
          }
        }
        continue;
      }

      // Profile line parsing
      if (trimmed.toLowerCase().includes('profile:') || trimmed.includes('🔗') || trimmed.includes('http')) {
        const match = trimmed.match(/(?:profile:\s*|\🔗\s*\*\*profile:\*\*\s*)(https?:\/\/[^\s\)]+)/i);
        if (match && match[1]) {
          currentProf.profileUrl = match[1].trim();
        } else {
          const mdUrlMatch = trimmed.match(/https?:\/\/[^\s\)]+/);
          if (mdUrlMatch && !currentProf.profileUrl) {
            currentProf.profileUrl = mdUrlMatch[0];
          }
        }
        continue;
      }

      // Non-bullet text after professor list starts
      if (trimmed === '' || (!trimmed.startsWith('-') && !trimmed.startsWith('*') && !trimmed.startsWith('🔬') && !trimmed.startsWith('📧') && !trimmed.startsWith('🔗'))) {
        if (professors.length > 0 && !trimmed.match(/^\d+[\.\)]/)) {
          footerLines.push(line);
          continue;
        }
      }
    }

    if (!inProfSection) {
      headerLines.push(line);
    }
  }

  if (currentProf && currentProf.name) {
    professors.push(finalizeProf(currentProf, professors.length));
  }

  return {
    headerText: headerLines.join('\n').trim(),
    professors,
    footerText: footerLines.join('\n').trim(),
  };
}

function finalizeProf(p: Partial<Professor>, index: number): Professor {
  return {
    id: `prof-${index}-${Date.now()}`,
    name: p.name || 'Faculty Member',
    title: p.title || 'Professor',
    research: p.research && p.research.length > 0 ? p.research : ['Faculty Research'],
    email: p.email || 'Not listed',
    profileUrl: p.profileUrl || '',
  };
}
