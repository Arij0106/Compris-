export type FileKind = 'pdf' | 'word' | 'excel' | 'ppt' | 'text';

export const ACCEPTED_EXTENSIONS: readonly string[] = [
  'pdf',
  'doc', 'docx', 'odt', 'rtf',
  'xls', 'xlsx', 'xlsm', 'csv', 'ods',
  'ppt', 'pptx', 'odp',
  'txt', 'md',
];

export const ACCEPT_ATTR: string = ACCEPTED_EXTENSIONS.map((e) => `.${e}`).join(',');

export function extOf(name: string): string {
  const i = name.lastIndexOf('.');
  return i < 0 ? '' : name.slice(i + 1).toLowerCase();
}

export function kindOf(ext: string): FileKind {
  if (ext === 'pdf') return 'pdf';
  if (['doc', 'docx', 'odt', 'rtf'].includes(ext)) return 'word';
  if (['xls', 'xlsx', 'xlsm', 'csv', 'ods'].includes(ext)) return 'excel';
  if (['ppt', 'pptx', 'odp'].includes(ext)) return 'ppt';
  return 'text';
}

export type SourceStatus = 'uploading' | 'ready' | 'error';

export interface CourseSource {
  id: string;
  name: string;
  size: number;
  ext: string;
  kind: FileKind;
  selected: boolean;
  status: SourceStatus;
  progress: number;
  courseId?: string;
  error?: string;
  file: File;
}

export type ReplyType = 'in_course' | 'out_of_course' | 'off_topic';

export interface Citation {
  page: number;
  chapitre: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'tutor';
  text: string;
  sources?: Citation[];
  type?: ReplyType;
  failed?: boolean;
}

export interface ChatReply {
  reply: string;
  sources: Citation[];
  type: ReplyType;
}

export interface QuizQuestion {
  id: string;
  question: string;
  choices: string[];
  concept: string;
  level: string;
}

export interface UploadUpdate {
  progress: number;
  courseId?: string;
}

/** Unité détectée par l'agent lors de l'analyse des cours. */
export interface AnalyzedUnit {
  id: string;
  title: string;
  summary?: string;
}

export type UnitStatus = 'todo' | 'current' | 'acquired' | 'gaps';

export interface Gap {
  concept: string;
  explanation: string;
}

export interface CourseUnit extends AnalyzedUnit {
  status: UnitStatus;
  score?: number;
  total?: number;
  gaps: Gap[];
}

export interface QuestionFeedback {
  question_id: string;
  correct: boolean;
  explanation: string;
}

/** Résultat de l'analyse des réponses d'une unité par l'agent. */
/** Résultat de l'analyse des réponses d'une unité par l'agent. */
export interface UnitEvaluation {
  score: number;
  total: number;
  acquired: boolean;
  gaps: Gap[];
  feedback: QuestionFeedback[];
  /** Fix #7 : synthèse pédagogique générée lorsque le chapitre est acquis. */
  synthesis?: string;
}

export interface QuizSession {
  questions: QuizQuestion[];
  answers: (number | null)[];
  index: number;
}

export type Stage =
  | 'idle'
  | 'analyzing'
  | 'quizLoading'
  | 'quiz'
  | 'evaluating'
  | 'result'
  | 'finished'
  | 'error';

export interface Notice {
  kind: 'info' | 'error';
  text: string;
}
