export interface Professor {
  id: string;
  name: string;
  title: string;
  research: string[];
  email: string;
  profileUrl: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  professors?: Professor[];
  headerText?: string;
  footerText?: string;
  toolCallsCount?: number;
  isError?: boolean;
}

export interface SessionData {
  user_id: string;
  session_id: string;
  greeting: string;
}
