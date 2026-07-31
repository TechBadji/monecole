/** Enveloppe de pagination renvoyée par DRF. */
export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type Role =
  | "SUPER_ADMIN"
  | "ADMIN"
  | "ACCOUNTANT"
  | "SECRETARY"
  | "TEACHER"
  | "PARENT";

export type Profile = {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  phone: string;
  /** Chemin relatif à l'API, pas à l'interface — voir `absolute()`. */
  photo: string | null;
  initials: string;
  role: Role;
  role_label: string;
  school: { id: number; name: string; currency: string } | null;
  permissions: Record<string, string[]>;
};

export type ClassRoom = {
  id: number;
  name: string;
  level: "PRESCHOOL" | "PRIMARY";
  order: number;
  capacity: number | null;
  student_count: number;
};

export type Student = {
  id: number;
  matricule: string;
  first_name: string;
  last_name: string;
  full_name: string;
  date_of_birth: string | null;
  sex: "M" | "F" | "";
  classroom: number;
  classroom_name: string;
  parent_name: string;
  parent_phone: string;
  status: string;
};

export type Series = {
  key: string;
  label: string;
  values: number[];
  total: number;
  weight?: number | null;
};

export type Period = { date: string; label: string };

export type Bilan = {
  year: string;
  periods: Period[];
  resources: Series[];
  total_resources: Series;
  charges: Series[];
  total_charges: Series;
  ebe: Series;
  cumulative_balance: { key: string; label: string; values: number[] };
  current_balance: number;
  headcount_by_class: { classroom: string; headcount: number; revenue: number }[];
  headcount_total: number;
  revenue_total: number;
};

export type Dashboard = {
  year: string;
  headcount: number;
  revenue: number;
  charges: number;
  ebe: number;
  current_balance: number;
  monthly: {
    periods: string[];
    resources: number[];
    charges: number[];
    cumulative_balance: number[];
  };
  top_expenses: { label: string; total: number }[];
  revenue_by_class: { classroom: string; headcount: number; revenue: number }[];
  budget_overruns: { category: string; budget: number; actual: number; overrun: number }[];
};

export type RegisterRow = {
  student: number;
  name: string;
  tuition: number;
  canteen: number;
  reinforcement: number;
  uniform: number;
  method: string;
  payment_date: string | null;
  recorded: boolean;
};

export type Register = {
  year: string;
  period: string;
  expected_tuition: number | null;
  expected_canteen: number | null;
  rows: RegisterRow[];
};

export type Expense = {
  id: number;
  operation_date: string;
  period: string;
  label: string;
  amount: number;
  transfer_fee: number;
  category: number;
  category_label: string;
  channel: string;
  status: "DRAFT" | "PENDING" | "APPROVED" | "REJECTED";
  invoice_number: string;
};

export type ExpenseCategory = { id: number; code: string; label: string; order: number };

export type SchoolYear = {
  id: number;
  label: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
};

export type Arrears = {
  year: string;
  count: number;
  results: {
    student: number;
    name: string;
    classroom: string;
    parent_phone: string;
    due: number;
    paid: number;
    arrears: number;
    months_elapsed: number;
  }[];
};
