export type LearningRole = "focus" | "context" | "discovery";

export interface IssueCard {
  id: number;
  title: string;
  teaser: string;
  category: string;
  source: string;
  article_count: number;
  created_at: string;
}

export interface QuizQuestion {
  quiz_id: string;
  kind: string;
  question: string;
  options: string[];
}

export interface DailyLearningItem {
  position: number;
  role: LearningRole;
  role_label: string;
  reason: string;
  issue: IssueCard;
  quiz: QuizQuestion;
  completed: boolean;
}

export interface DailyLearning {
  learning_date: string;
  items: DailyLearningItem[];
  completed_count: number;
  total_count: number;
  is_complete: boolean;
  personalized: boolean;
}

export interface ReaderCard {
  head: string;
  paragraphs: string[];
}

export interface IssueTerm {
  name: string;
  definition: string;
  aliases: string[];
  source_label: string | null;
  source_title: string | null;
  source_url: string | null;
  source_page: number | null;
  original_url: string | null;
  ai_generated: boolean;
  verification_status: string;
}

export interface SourceArticle {
  id: string;
  title: string;
  url: string;
  news_source: string;
  published_at: string | null;
}

export interface IssueDetail extends IssueCard {
  cards: ReaderCard[];
  terms: IssueTerm[];
  sources: SourceArticle[];
}

export interface DailyQuizResult {
  issue_id: number;
  quiz_id: string;
  selected_index: number;
  answer_index: number;
  is_correct: boolean;
  explanation: string;
}

export interface Sector {
  id: number;
  name_ko: string;
  name_en: string;
  wics_code: string;
  gics_code: string;
  industry_groups: string[];
}

export interface StoredInterests {
  sectorIds: number[];
  savedAt: string;
}

export interface StoredDailyPlan {
  learningDate: string;
  interestKey: string;
  learning: DailyLearning;
  completedIssueIds: number[];
}
