export interface Role {
  id: number;
  key: string;
  label: string;
  description: string;
  color: string;
  view: string[];
  edit: string[];
  stages: string[];
  can_approve: boolean;
  all_sites: boolean;
  builtin: boolean;
  active: boolean;
  user_count?: number;
}

export interface Me {
  id: number;
  mobile: string;
  name: string;
  email: string;
  role: Role | null;
  is_admin: boolean;
  sites: number[];
  modules_view: string[];
  modules_edit: string[];
}

export interface User {
  id: number;
  mobile: string;
  name: string;
  email: string;
  role: number | null;
  role_key: string;
  role_label: string;
  sites: number[];
  is_active: boolean;
  alert_whatsapp: boolean;
  alert_email: boolean;
  alert_sms: boolean;
  last_login: string | null;
}

export interface Site {
  id: number;
  code: string;
  name: string;
  address: string;
  active: boolean;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface IndentRow {
  id: number;
  number: string;
  site: number;
  site_name: string;
  item: string;
  item_code: string;
  unit: string;
  qty: string;
  approved_qty: string | null;
  need_by: string | null;
  priority: "normal" | "urgent" | "critical";
  status: string;
  stage: string;
  stage_label: string;
  pstatus: string;
  pstage: string;
  waiting_with: string;
  purchase_with: string;
  raised_by: number;
  raised_by_name: string;
  po_no: string;
  po_vendor: string;
  po_expected: string | null;
  stage_entered_at: string | null;
  allowed_actions: string[];
  created_at: string;
}

export interface IndentEvent {
  id: number;
  action: string;
  label: string;
  lane: string;
  stage: string;
  from_status: string;
  to_status: string;
  to_stage: string;
  by_name: string;
  at: string;
  remarks: string;
  qty: string | null;
  qty_to: string | null;
  grn_no: string;
  inspection: string;
}

export interface Step {
  key: string;
  n: string;
  label: string;
  short?: string;
  dept?: string;
  lane?: string;
  state: "done" | "current" | "todo";
}

export interface Quote {
  vendor?: string;
  rate?: number | string;
  gst?: number | string;
  freight?: number | string;
  delivery_days?: number | string;
  terms?: string;
}

export interface IndentDetail extends IndentRow {
  purpose: string;
  est_rate: string | null;
  issued_qty: string | null;
  purchase_qty: string | null;
  received_qty: string | null;
  balance_cancelled: string | null;
  quotes: Quote[];
  vendor_final: string;
  rate: string | null;
  po_date: string | null;
  po_rate: string | null;
  tracking: string;
  issued_to: string;
  inv_no: string;
  inv_amount: string | null;
  paid_on: string | null;
  stock_note: string;
  spec_note: string;
  history: IndentEvent[];
  steps: Step[];
  can_edit: boolean;
  action_fields: Record<string, string[]>;
  [key: string]: unknown;
}

export interface WorkflowMeta {
  stages: { n: string; key: string; lane: string; label: string; short: string; dept: string; actions: string[]; required: boolean; can_qty: boolean }[];
  action_labels: Record<string, string>;
  needs_remark: string[];
  settings: { stages: Record<string, { on: boolean }>; mgmt_limit: string; mgmt_never: boolean };
}

export interface Notification {
  id: number;
  kind: string;
  title: string;
  body: string;
  link: string;
  created_at: string;
  read_at: string | null;
}
