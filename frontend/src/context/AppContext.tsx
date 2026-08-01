import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
import { api } from '../services/api';
import { DocumentItem, OCRReviewData, DocProcessingStatus } from '../types';

// While any document is mid-pipeline, every page showing the list needs to keep up.
const ACTIVE_STATUSES: DocProcessingStatus[] = ['uploaded', 'processing', 'indexing'];
const REFRESH_MS = 3000;

interface UploadState {
  isUploading: boolean;
  uploadProgress: number;
  uploadedDocId: string | null;
}

interface AppContextType {
  // Documents
  documents: DocumentItem[];
  documentsLoading: boolean;
  fetchDocuments: () => Promise<void>;

  // Upload state (persists across tab switches)
  uploadState: UploadState;
  setUploadState: React.Dispatch<React.SetStateAction<UploadState>>;

  // Review data (persists across tab switches)
  reviewData: OCRReviewData | null;
  setReviewData: React.Dispatch<React.SetStateAction<OCRReviewData | null>>;
  editedText: string;
  setEditedText: React.Dispatch<React.SetStateAction<string>>;
  activeReviewDocId: string | null;
  setActiveReviewDocId: React.Dispatch<React.SetStateAction<string | null>>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  // Global document list
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);

  // Persisted upload state
  const [uploadState, setUploadState] = useState<UploadState>({
    isUploading: false,
    uploadProgress: 0,
    uploadedDocId: null,
  });

  // Persisted review state
  const [reviewData, setReviewData] = useState<OCRReviewData | null>(null);
  const [editedText, setEditedText] = useState('');
  const [activeReviewDocId, setActiveReviewDocId] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    setDocumentsLoading(true);
    try {
      const res = await api.get('/documents');
      setDocuments(res.data);
    } catch (err) {
      console.error('Failed to load documents', err);
    } finally {
      setDocumentsLoading(false);
    }
  }, []);

  // Keep the shared list live so dashboard/library badges don't go stale mid-pipeline.
  const hasActiveWork = documents.some((d) => ACTIVE_STATUSES.includes(d.status));
  useEffect(() => {
    if (!hasActiveWork) return;
    const timer = setInterval(fetchDocuments, REFRESH_MS);
    return () => clearInterval(timer);
  }, [hasActiveWork, fetchDocuments]);

  return (
    <AppContext.Provider
      value={{
        documents,
        documentsLoading,
        fetchDocuments,
        uploadState,
        setUploadState,
        reviewData,
        setReviewData,
        editedText,
        setEditedText,
        activeReviewDocId,
        setActiveReviewDocId,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useApp = () => {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useApp must be used within AppProvider');
  }
  return context;
};
