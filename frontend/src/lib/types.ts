export type Role = "employee" | "manager" | "hr" | "admin";

export interface Me {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  employee_id: number | null;
  position: string | null;
  department: string | null;
}

export interface SystemInfo {
  llm_mode: "local" | "external" | "fake";
  llm_model: string;
  pseudonymize: boolean;
  data_leaves_server: boolean;
  k_anonymity: number;
  scale: { value: number; label: string }[];
  legal_basis: string;
}

export interface TeamMember {
  id: number;
  full_name: string;
  position: string;
  department: string | null;
  notes_count: number;
  last_note_date: string | null;
  reminder: boolean;
  current_review: { id: number; status: ReviewStatus } | null;
}

export interface Criterion {
  id: number;
  code: string;
  name: string;
  description: string;
  behavioral_indicators: string[];
  mandatory_for: string[];
}

export interface Cycle {
  id: number;
  name: string;
  period_start: string;
  period_end: string;
  status: "open" | "closed";
}

export interface NoteTag {
  criterion_id: number;
  code: string;
  name: string;
  confidence: number;
  assigned_by: "ai" | "human";
}

export interface Note {
  id: number;
  employee_id: number;
  author_id: number;
  author_name: string | null;
  date: string;
  text: string;
  sentiment: "positive" | "neutral" | "negative" | null;
  source: "manager" | "self";
  shared_with_employee: boolean;
  classified: boolean;
  criteria: NoteTag[];
}

export interface EmployeeDetail {
  id: number;
  full_name: string;
  position: string;
  department: string | null;
  manager_name: string | null;
  position_description: string;
  sheet_type: string;
  is_civil_servant: boolean;
  contract_type?: "mianowanie" | "nieokreslony" | "okreslony";
  senior_position?: boolean;
  reviews: { id: number; status: ReviewStatus; cycle_id: number; cycle_name: string; overall_level: string | null; result: string | null }[];
}

export type ReviewStatus = "criteria" | "observation" | "draft" | "submitted" | "discussed" | "final" | "acknowledged" | "objection";

export interface ReviewCriterion {
  criterion_id: number;
  code: string;
  name: string;
  description: string;
  indicators: string[];
  is_additional: boolean;
  score: number | null;
  justification: string;
  source_note_ids: number[];
}

export interface Review {
  id: number;
  status: ReviewStatus;
  sheet_type: string;
  cycle_id: number;
  period_start: string;
  period_end: string;
  conversation_date: string | null;
  employee: { id: number; full_name: string; position: string; position_description: string; is_civil_servant: boolean; senior_position?: boolean };
  reviewer: { id: number; full_name: string };
  criteria: ReviewCriterion[];
  summary: { average: number; level: string; result: string | null; complete: boolean } | null;
  justification: string;
  ipr_conclusions: string;
  self_assessment_submitted: boolean;
  self_assessment_submitted_at: string | null;
  ipr_id: number | null;
  scale: { value: number; label: string }[];
  updated_at: string;
  // pola arkusza (części I-III) i proces
  office: { name: string; city: string; objection_body: string };
  employee_form: FormPerson;
  reviewer_form: FormPerson;
  attempt: number;
  assessment_invited_at: string | null;
  assessment_confirmed_at: string | null;
  opening_conversation_date: string | null;
  opening_notes: string;
  criteria_reviewer_confirmed_at: string | null;
  criteria_reviewer_place: string;
  criteria_employee_confirmed_at: string | null;
  criteria_employee_place: string;
  due_date_history: { from?: string | null; date: string; reason: string; note?: string; at: string }[];
  prev_result: "pozytywna" | "negatywna" | "brak" | null;
  prev_level: string | null;
  prev_date: string | null;
  promotion_request: "tak" | "nie" | "nie_dotyczy";
  appointment_year: number | null;
  civil_grade: number | null;
  civil_grade_date: string | null;
  promotion_target: string | null;
  civil_grade_label?: string | null;
  signature_method?: "system" | "wydruk" | "elektroniczny";
  objection_body?: string | null;
  promotion_justification: string;
  reviewer_place: string;
  reviewer_signed_at: string | null;
  employee_place: string;
  acknowledged_at: string | null;
  ack_fiction: boolean;
  ack_fiction_note: string;
  objection_at: string | null;
  objection_text: string;
  objection_decision: "odrzucony" | "zmiana" | "ponowne_sporzadzenie" | null;
  objection_decided_at: string | null;
  deadlines: {
    criteria_deadline: string | null;
    due_date: string | null;
    can_change_due_date: boolean;
    is_repeat_review?: boolean;
    objection_deadline: string | null;
    objection_open: boolean;
    repeat_review_date: string | null;
    obligatory_promotion: boolean;
    promotion_deadline: string | null;
    termination_risk?: boolean;
  };
}

export interface FormPerson {
  first_name: string;
  last_name: string;
  full_name: string;
  department: string;
  position: string;
}

export interface Reminder {
  kind: string;
  title: string;
  detail: string;
  due: string | null;
  severity: "critical" | "warning" | "info";
  link: string;
}

export interface Sentence {
  text: string;
  source_note_ids: number[];
  unsupported?: boolean;
}

export interface Suggestion<P = Record<string, unknown>> {
  id: number;
  kind: string;
  review_id: number;
  criterion_id: number | null;
  payload: P;
  model: string;
  prompt_version: string;
  status: "pending" | "accepted" | "edited" | "rejected" | "info";
  final_payload: Record<string, unknown> | null;
  created_at: string;
}

export interface DraftPayload {
  sentences: Sentence[];
  proposed_score: number | null;
  rationale: string;
  notes_used: number;
}

export interface Warning {
  code: string;
  severity: "critical" | "warning" | "info";
  criterion_id: number | null;
  title: string;
  message: string;
  suggestion: string;
  evidence: (string | number)[];
  source: "rule" | "ai";
}

export interface CompareRow {
  criterion_id: number;
  code: string;
  name: string;
  manager_score: number | null;
  self_score: number | null;
  comment: string;
  diff: number | null;
  level: "major" | "minor" | "agree" | null;
}

export interface ComparePayload {
  rows: CompareRow[];
  questions: string[];
  summary: string;
}

export interface SelfAssessment {
  review_id: number;
  criteria: { criterion_id: number; code: string; name: string; description: string; indicators: string[] }[];
  items: Record<string, { score: number | null; comment: string }>;
  summary: string;
  submitted_at: string | null;
  open: boolean;
}

export interface IPRGoal {
  id?: number;
  criterion_id: number | null;
  criterion_name?: string | null;
  goal: string;
  actions: string;
  success_measure: string;
  deadline: string | null;
  training: { id: number; code: string; title: string; hours: number; format: string } | null;
}

export interface IPR {
  id: number;
  review_id: number;
  status: "draft" | "established" | "accepted" | "approved";
  established_at: string | null;
  accepted_at: string | null;
  can_edit?: boolean;
  can_accept?: boolean;
  can_approve?: boolean;
  summary: string;
  employee: { id: number; full_name: string; position: string };
  approved_at: string | null;
  ai: { model: string; prompt_version: string; status: string } | null;
  goals: IPRGoal[];
}

export interface Training {
  id: number;
  code: string;
  title: string;
  criterion_codes: string[];
  format: string;
  hours: number;
}

export interface Overview {
  cycle_id: number | null;
  distribution: {
    k: number;
    total: { n: number; levels: Record<string, number> };
    departments: { department: string; n: number; hidden: boolean; levels: Record<string, number | null>; top_share: number | null; flag: string | null }[];
  };
  competency_gaps: { k: number; criteria: { criterion_id: number; code: string; name: string; n: number; average: number | null; hidden: boolean }[] };
  reviewer_calibration: { reviewer_id: number; reviewer_name: string; n: number; average: number | null; office_average: number; delta: number; flag: string | null; hidden: boolean }[];
  gender_gap: { k: number; groups: Record<string, { n: number; average: number | null }>; gap_k_minus_m: number | null };
  ai_adoption: { by_kind: Record<string, Record<string, number>>; by_model: Record<string, number> };
}

export interface TeamStats {
  date_from: string | null;
  date_to: string | null;
  employees: {
    employee_id: number;
    full_name: string;
    position: string;
    department: string | null;
    reviews: {
      review_id: number;
      cycle_id: number;
      cycle: string;
      period_start: string;
      period_end: string;
      score: number | null;
      level: string | null;
      result: string | null;
      status: ReviewStatus;
      drawn_up: string;
    }[];
    n: number;
    average: number | null;
    latest_level: string | null;
    latest_result: string | null;
    latest_score: number | null;
  }[];
  summary: {
    n_employees: number;
    n_reviews: number;
    average: number | null;
    levels: Record<string, number>;
    results: Record<string, number>;
    criteria: { code: string; name: string; average: number; n: number }[];
  };
}
