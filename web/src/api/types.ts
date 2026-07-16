// Mirrors ingestion/metadata.py, rag/chain.py, and api/schemas.py exactly --
// keep these in sync with the backend Pydantic models if either changes.

export type DocType =
  | "loan_agreement"
  | "invoice"
  | "kyc_form"
  | "financial_statement"
  | "other";

export const DOC_TYPES: { value: DocType; label: string }[] = [
  { value: "loan_agreement", label: "Loan Agreement" },
  { value: "invoice", label: "Invoice" },
  { value: "kyc_form", label: "KYC Form" },
  { value: "financial_statement", label: "Financial Statement" },
  { value: "other", label: "Other" },
];

// ingestion/metadata.py: SourceRef
export interface SourceRef {
  doc_id: string;
  filename: string;
  page_number: number;
  section: string | null;
  chunk_id: string;
  char_start: number;
  char_end: number;
}

// rag/chain.py: Citation
export interface Citation {
  source: SourceRef;
  snippet: string;
}

// api/schemas.py: QueryResponse
export interface QueryResponse {
  answer: string;
  citations: Citation[];
}

// api/schemas.py: IngestResponse
export interface IngestResponse {
  doc_id: string;
  doc_type: DocType;
  num_pages: number;
  num_chunks: number;
  pii_chunks_redacted: number;
}

// api/schemas.py: HealthResponse
export interface HealthResponse {
  status: string;
  vectorstore_backend: string;
  llm_provider: string;
  embedding_provider: string;
}
