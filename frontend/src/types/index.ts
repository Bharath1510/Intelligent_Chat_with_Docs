export interface DocumentItem {
  id: string;
  filename: string;
  file_size: number;
  content_type: string;
  status: 'uploaded' | 'processing' | 'ocr_ready' | 'indexed' | 'failed';
  total_pages: number;
  created_at: string;
  updated_at?: string;
}

export interface OCRBlock {
  block_id: number;
  text: string;
  confidence: number;
  bbox?: number[][];
}

export interface OCRReviewData {
  id: string;
  filename: string;
  status: string;
  ocr_raw_text: string;
  ocr_edited_text: string;
  blocks: OCRBlock[];
  total_pages: number;
}

export interface Citation {
  document_id: string;
  document_name: string;
  page_number: number;
  snippet: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  citations?: Citation[];
  created_at: string;
}

export interface ChatSession {
  id: string;
  title: string;
  document_ids?: string[] | null;
  created_at: string;
  updated_at?: string;
}
