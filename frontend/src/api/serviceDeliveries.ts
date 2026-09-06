import type { FilingDocument } from './filings';

export interface DeliveryContact {
  participant_id: number;
  name: string;
  role: string;
  represented_party_name: string | null;
  contact_id: number | null;
  version: number | null;
  method: string | null;
  email: string | null;
  address: string | null;
  authority: string | null;
  issues: string[];
}

export interface DeliveryOptions {
  enabled: boolean;
  source_transaction_id: string;
  case_number: string;
  case_title: string;
  court_name: string;
  documents: FilingDocument[];
  recipients: DeliveryContact[];
  total: number;
  page_size: number;
}

export interface DeliveryDetails {
  id: string;
  packet_id: string;
  source_transaction_id: string;
  filing_id: number;
  sender: string;
  created_at: string;
  court_name: string;
  case_number: string;
  case_title: string;
  documents: FilingDocument[];
  contact: { name: string; email: string; authority: string };
  delivery_status: string;
  last_error: string | null;
  message_id: string | null;
  acknowledged_at: string | null;
  can_acknowledge: boolean;
  can_retry: boolean;
}
