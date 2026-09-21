export type UserRole = "admin" | "end_user";
export type AuthProvider = "local" | "oidc" | "saml";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: UserRole;
  provider: AuthProvider;
  is_active: boolean;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Category {
  id: string;
  name: string;
  slug: string;
  description: string;
  icon: string;
  sort_order: number;
  portal_count?: number;
  created_at: string;
}

export type FieldType =
  | "text"
  | "textarea"
  | "number"
  | "select"
  | "multiselect"
  | "date"
  | "checkbox"
  | "email";

export interface FieldDefinition {
  name: string;
  label: string;
  type: FieldType;
  required: boolean;
  placeholder: string;
  help_text: string;
  options: string[];
  default: string | null;
  ado_field_ref: string | null;
}

export interface Portal {
  id: string;
  slug: string;
  name: string;
  description: string;
  icon: string;
  category_id: string | null;
  category_name: string | null;
  ado_project: string | null;
  work_item_type: string;
  fields: FieldDefinition[];
  is_active: boolean;
  created_at: string;
}

export interface PortalSummary {
  id: string;
  slug: string;
  name: string;
  description: string;
  icon: string;
  category_name: string | null;
}

export interface CatalogGroup {
  category: string;
  icon: string;
  sort_order: number;
  portals: PortalSummary[];
}

export type SyncStatus = "pending" | "syncing" | "synced" | "failed";

export interface Ticket {
  id: string;
  portal_id: string;
  title: string;
  description: string;
  field_values: Record<string, unknown>;
  submitter_email: string;
  ado_work_item_id: number | null;
  ado_url: string | null;
  ado_state: string | null;
  sync_status: SyncStatus;
  sync_attempts: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface TicketComment {
  id: number;
  text: string;
  author: string;
  author_email: string | null;
  created_at: string;
}

export interface TicketListItem {
  id: string;
  title: string;
  portal_id: string;
  ado_work_item_id: number | null;
  ado_url: string | null;
  ado_state: string | null;
  sync_status: SyncStatus;
  created_at: string;
}

export interface AuthProviders {
  local: boolean;
  oidc: boolean;
  saml: boolean;
}

export interface AdoProject {
  id: string;
  name: string;
}

export interface AdoProjectsResponse {
  configured: boolean;
  default_project?: string | null;
  projects: AdoProject[];
  error: string | null;
}

export interface AdoWorkItemType {
  name: string;
  reference_name: string;
}

export interface AdoWorkItemTypesResponse {
  configured: boolean;
  work_item_types: AdoWorkItemType[];
  error: string | null;
}
