export interface HoldingItem {
  portfolio_id: string;
  identifier: string;
  security_name: string;
  asset_class: string;
  sector: string | null;
  quantity: number;
  avg_cost_per_unit: number;
  total_cost: number;
  realized_pnl: number;
  dividend_income: number;
  current_price: number | null;
  current_value: number | null;
  unrealized_pnl: number | null;
  day_change_pct: number | null;
  as_of: string;
}

export interface PortfolioSummary {
  portfolio_id: string;
  portfolio_type: string;
  provider_name: string;
  current_value: number;
  total_invested: number;
  xirr: number | null;
  unrealized_pnl: number;
  abs_return_pct: number | null;
}

export interface EntitySummary {
  entity_id: string;
  entity_name: string;
  entity_type: string;
  total_value: number;
  portfolios: PortfolioSummary[];
}

export interface SummaryResponse {
  total_net_worth: number;
  total_invested: number;
  total_unrealized_pnl: number;
  entities: EntitySummary[];
}

export interface TransactionItem {
  event_id: string;
  portfolio_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  event_date: string;
  version: number;
  created_at: string;
}

export interface PaginatedTransactions {
  items: TransactionItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AlertItem {
  id: string;
  source: 'threshold' | 'reconciliation';
  alert_type: string;
  severity: 'warning' | 'critical';
  message: string;
  portfolio_id: string;
  identifier: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  dismissed_at: string | null;
}
