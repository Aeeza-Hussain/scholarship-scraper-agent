import type { Professor } from '../types';

// Non-professor keyword blacklist: If a candidate name contains these, it's a prompt/question, not a person
const FORBIDDEN_NAME_KEYWORDS = [
  'department',
  'dept',
  'university',
  'college',
  'school',
  'research',
  'interest',
  'interests',
  'academic',
  'title',
  'titles',
  'required',
  'optional',
  'please',
  'provide',
  'specify',
  'url',
  'homepage',
  'website',
  'example',
  'e.g.',
  'criterion',
  'criteria',
  'step',
  'detail',
  'details',
];

// Valid academic titles
const VALID_TITLE_REGEX = /\b(assistant\s+professor|associate\s+professor|adjunct\s+professor|visiting\s+professor|full\s+professor|professor|lecturer|senior\s+lecturer|instructor|teaching\s+professor|chair\s+professor|dean|fellow|researcher|scientist|faculty\s+member)\b/i;

/**
 * Parses raw text from the agent response to extract structured professor card data
 * ONLY if the response contains genuine matching faculty listings.
 */
export function parseProfessorResponse(text: string): {
  headerText: string;
  professors: Professor[];
  footerText: string;
} {
  if (!text) return { headerText: '', professors: [], footerText: '' };

  // Quick check: If the text is clearly asking questions or prompt instructions, don't parse as professors
  const lowerText = text.toLowerCase();
  const isQuestionOrPrompt =
    (lowerText.includes('please provide') || lowerText.includes('please share') || lowerText.includes('remaining required details')) &&
    !lowerText.includes('i found') &&
    !lowerText.includes('matching your criteria');

  if (isQuestionOrPrompt) {
    return { headerText: text, professors: [], footerText: '' };
  }

  const lines = text.split('\n');
  const professors: Professor[] = [];
  const headerLines: string[] = [];
  const footerLines: string[] = [];

  let currentProf: Partial<Professor> | null = null;
  let inProfSection = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Match numbered candidate line: "1. **Dr. Ali Khan** — Assistant Professor"
    const profHeaderMatch = trimmed.match(/^\d+[\.\)]\s*(?:\*\*)?(.*?)(?:\*\*)?\s*[\—\–\-]\s*(.*)$/);

    if (profHeaderMatch) {
      let rawName = profHeaderMatch[1].replace(/\*\*/g, '').trim();
      let rawTitle = profHeaderMatch[2].replace(/\*\*/g, '').trim();

      // Clean up markdown bolds and whitespace
      rawName = rawName.replace(/^[\s\*]+|[\s\*]+$/g, '');
      const lowerName = rawName.toLowerCase();

      // Strict Validation: Reject if the name contains question/requirement words
      const isBlacklisted = FORBIDDEN_NAME_KEYWORDS.some((kw) => lowerName.includes(kw));
      // Strict Validation: Title must match a legitimate academic title
      const hasValidTitle = VALID_TITLE_REGEX.test(rawTitle);

      if (!isBlacklisted && hasValidTitle && rawName.length > 2 && rawName.length < 60) {
        inProfSection = true;
        if (currentProf && currentProf.name) {
          professors.push(finalizeProf(currentProf, professors.length));
        }

        currentProf = {
          name: rawName,
          title: rawTitle,
          research: [],
          email: '',
          profileUrl: '',
        };
        continue;
      }
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
            .filter((s) => s.length > 0 && s.toLowerCase() !== 'not listed' && !s.toLowerCase().includes('required'));
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

      // Text after professor list terminates the active professor item
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

  // If no valid professors were detected, treat the entire message as pure text
  if (professors.length === 0) {
    return {
      headerText: text,
      professors: [],
      footerText: '',
    };
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
