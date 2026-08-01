// uploaded -> processing (OCR) -> ocr_ready -> indexing -> indexed | failed
export type DocProcessingStatus =
  | 'uploaded'
  | 'processing'
  | 'ocr_ready'
  | 'indexing'
  | 'indexed'
  | 'failed';

export interface DocumentItem {
  id: string;
  filename: string;
  file_size: number;
  content_type: string;
  status: DocProcessingStatus;
  total_pages: number;
  error_message?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface OCRBlock {
  block_id: number;
  page?: number;
  text: string;
  confidence?: number | null;
  bbox?: number[][] | null;
  source?: 'paddleocr' | 'pdf_text_layer';
}

export interface OCRReviewData {
  id: string;
  filename: string;
  status: DocProcessingStatus;
  ocr_raw_text: string;
  ocr_edited_text: string;
  blocks: OCRBlock[];
  total_pages: number;
  error_message?: string | null;
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
