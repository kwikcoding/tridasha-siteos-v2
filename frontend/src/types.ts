export interface Role {
  id: number;
  key: string;
  label: string;
  description: string;
  color: string;
  permissions: string[];
  view: string[];
  edit: string[];
  stages: string[];
  step_actions: Record<string, string[]>;
  can_approve: boolean;
  all_sites: boolean;
  builtin: boolean;
  active: boolean;
  user_count?: number;
}

export interface Me {
  id: number;
  employee_id: string | null;
  mobile: string;
  name: string;
  email: string;
  designation: string;
  department_name: string;
  manager_name: string;
  role: Role | null;
  roles: { key: string; label: string }[];
  is_admin: boolean;
  sites: number[];
  permissions: string[];
  modules_view: string[];
  modules_edit: string[];
  stages: string[];
  must_change_password: boolean;
  last_login: string | null;
}

export interface User {
  id: number;
  employee_id: string | null;
  mobile: string;
  name: string;
  email: string;
  designation: string;
  department: number | null;
  department_name: string;
  reporting_manager: number | null;
  manager_name: string;
  role: number | null;
  role_key: string;
  role_label: string;
  extra_roles: number[];
  all_role_labels: string[];
  sites: number[];
  is_active: boolean;
  must_change_password: boolean;
  alert_whatsapp: boolean;
  alert_email: boolean;
  alert_sms: boolean;
  date_joined: string;
  last_login: string | null;
}

export interface Department {
  id: number;
  name: string;
  code: string;
  head: number | null;
  head_name: string;
  active: boolean;
  staff_count: number;
}

export interface PermCatalogue {
  modules: { group: string; modules: { key: string; label: string; perms: { code: string; verb: string; label: string; admin_only: boolean }[] }[] }[];
  steps: { key: string; n: string; short: string; dept: string; lane: string; actions: string[] }[];
}

export interface Pending {
  indents: number;
  purchases: number;
  low_stock: number;
  total: number;
}

export interface AuditEntry {
  id: number;
  at: string;
  actor: number | null;
  actor_name: string;
  action: string;
  target_type: string;
  target_id: string;
  summary: string;
  changes: Record<string, unknown>;
  ip: string | null;
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
  changes?: Record<string, unknown>;
  override: boolean;
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
  inv_gst: string | null;
  inv_expected: string | null;
  pay_auth_amount: string | null;
  paid_total: string | null;
  paid_on: string | null;
  money: {
    expected: number; invoice_total: number; variance: number | null; within_tolerance: boolean; tolerance_pct: number;
    payable: number; authorised: number | null; paid: number; outstanding: number;
  };
  stock_note: string;
  spec_note: string;
  material: number | null;
  stock_at_site: string | null;
  stock_entries: { id: number; date: string; kind: string; qty: string; ref: string; note: string }[];
  history: IndentEvent[];
  steps: Step[];
  can_edit: boolean;
  action_fields: Record<string, string[]>;
  [key: string]: unknown;
}

export interface WorkflowMeta {
  stages: { n: string; key: string; lane: string; label: string; short: string; dept: string; actions: string[]; approve_label: string; required: boolean; can_qty: boolean }[];
  action_labels: Record<string, string>;
  button_labels: Record<string, string>;
  needs_remark: string[];
  settings: { stages: Record<string, { on: boolean }>; mgmt_limit: string; mgmt_never: boolean; inv_tolerance_pct?: number };
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

export interface Material {
  id: number;
  code: string;
  name: string;
  category: string;
  unit: string;
  spec: string;
  hsn: string;
  gst_rate: string | null;
  std_rate: string | null;
  reorder_level: string | null;
  active: boolean;
  balance?: string;
}

export interface RegisterItem {
  id: number;
  item_id: string;
  trade: string;
  system: string;
  item: string;
  unit: string;
  spec: string;
  applicability: string;
  zone: string;
  req_qty: string | null;
  grade: string;
  make: string;
  vendor: string;
  boq_ref: string;
  status: string;
  required_by: string | null;
  remarks: string;
  material: number | null;
  material_code: string;
  material_name: string;
}

export interface RegisterStats {
  total: number;
  applicability: Record<string, number>;
  status: Record<string, number>;
  trades: { name: string; count: number }[];
  linked: number;
}

export interface StockEntry {
  id: number;
  site: number;
  site_name: string;
  material: number;
  material_code: string;
  material_name: string;
  unit: string;
  date: string;
  kind: "IN" | "OUT" | "ADJ";
  qty: string;
  rate: string | null;
  source: string;
  indent: number | null;
  indent_number: string;
  ref: string;
  party: string;
  note: string;
  by_name: string;
}

export interface StockBalance {
  material: number;
  code: string;
  name: string;
  category: string;
  unit: string;
  balance: string;
  received: string;
  issued: string;
  last_movement: string | null;
  reorder_level: string | null;
  low: boolean;
}

export interface ImportResult {
  kind: string;
  columns: Record<string, string>;
  errors: { line: number; message: string }[];
  error_count: number;
  create: number;
  update: number;
  unchanged: number;
  committed: boolean;
  sample_new: string[];
  sample_changed: { key: string; fields: string[] }[];
}
