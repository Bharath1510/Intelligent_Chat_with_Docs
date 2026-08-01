import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { useApp } from '../context/AppContext';
import { DocProcessingStatus } from '../types';
import {
  Upload, FileText, CheckCircle, RefreshCw, Edit3, Eye, Loader2, AlertCircle, RotateCcw,
} from 'lucide-react';

const POLL_MS = 2000;
// Statuses the backend is still working on — keep polling while we see them.
const ACTIVE_STATUSES: DocProcessingStatus[] = ['uploaded', 'processing', 'indexing'];

const STAGE_LABEL: Record<string, string> = {
  uploaded: 'Queued for OCR…',
  processing: 'Running PaddleOCR…',
  indexing: 'Chunking & embedding into the vector store…',
};

export const UploadReviewPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const docId = searchParams.get('doc');
  const navigate = useNavigate();

  const {
    uploadState,
    setUploadState,
    reviewData,
    setReviewData,
    editedText,
    setEditedText,
    activeReviewDocId,
    setActiveReviewDocId,
    fetchDocuments,
  } = useApp();

  const [loadingReview, setLoadingReview] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [docStatus, setDocStatus] = useState<DocProcessingStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [chunkCount, setChunkCount] = useState(0);
  const [mobileTab, setMobileTab] = useState<'original' | 'text'>('text');
  // Bumped to restart the poller after confirm/retry queues new backend work.
  const [pollToken, setPollToken] = useState(0);

  // Read inside polling callbacks without re-subscribing the effect on every keystroke.
  const activeDocRef = useRef(activeReviewDocId);
  useEffect(() => {
    activeDocRef.current = activeReviewDocId;
  }, [activeReviewDocId]);

  const loadReviewData = useCallback(
    async (id: string) => {
      setLoadingReview(true);
      try {
        const { data } = await api.get(`/documents/${id}/review`);
        setReviewData(data);
        setDocStatus(data.status);
        setStatusError(data.error_message ?? null);
        // Only seed the editor when this is a different document, so edits survive navigation.
        if (activeDocRef.current !== id) {
          setEditedText(data.ocr_edited_text || data.ocr_raw_text || '');
          setActiveReviewDocId(id);
          activeDocRef.current = id;
        }
      } catch (err) {
        console.error('Failed to fetch review data', err);
        setStatusError('Could not load the extracted text for this document.');
      } finally {
        setLoadingReview(false);
      }
    },
    [setReviewData, setEditedText, setActiveReviewDocId]
  );

  // Single source of truth for status. Runs for EVERY doc id — including the one
  // we just uploaded — and follows it through OCR and indexing to a terminal state.
  useEffect(() => {
    if (!docId) {
      setDocStatus(null);
      setStatusError(null);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      try {
        const { data } = await api.get(`/documents/${docId}/status`);
        if (cancelled) return;

        setDocStatus(data.status);
        setStatusError(data.error_message ?? null);
        setChunkCount(data.chunk_count ?? 0);

        if (ACTIVE_STATUSES.includes(data.status)) {
          // setTimeout, not setInterval: a slow response can never stack requests.
          timer = setTimeout(tick, POLL_MS);
        } else {
          await loadReviewData(docId);
          fetchDocuments();
        }
      } catch (err) {
        if (cancelled) return;
        console.error('Failed to check doc status', err);
        setStatusError('Lost contact with the server — retrying…');
        timer = setTimeout(tick, POLL_MS);
      }
    };

    tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [docId, pollToken, loadReviewData, fetchDocuments]);

  const handleFileUpload = async (file: File) => {
    setUploadState({ isUploading: true, uploadProgress: 0, uploadedDocId: null });
    const formData = new FormData();
    formData.append('file', file);

    try {
      const { data } = await api.post('/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          const pct = e.total ? Math.round((e.loaded / e.total) * 100) : 0;
          setUploadState((prev) => ({ ...prev, uploadProgress: pct }));
        },
      });

      setUploadState({ isUploading: false, uploadProgress: 100, uploadedDocId: data.document_id });

      // Clear the previous document's review state before the poller takes over.
      setReviewData(null);
      setEditedText('');
      setActiveReviewDocId(null);
      activeDocRef.current = null;
      setDocStatus('uploaded');
      setStatusError(null);

      navigate(`/upload?doc=${data.document_id}`, { replace: true });
      fetchDocuments();
    } catch (err: any) {
      setUploadState({ isUploading: false, uploadProgress: 0, uploadedDocId: null });
      alert(err.response?.data?.detail || 'File upload failed');
    }
  };

  const handleConfirmAndIndex = async () => {
    if (!reviewData || !docId) return;
    setSubmitting(true);
    try {
      await api.put(`/documents/${docId}/confirm`, { edited_text: editedText });
      setDocStatus('indexing');
      setStatusError(null);
      setPollToken((n) => n + 1); // restart the poller to follow indexing to completion
    } catch (err: any) {
      alert('Confirmation failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetry = async () => {
    if (!docId) return;
    setSubmitting(true);
    try {
      await api.post(`/documents/${docId}/reprocess`);
      setDocStatus('uploaded');
      setStatusError(null);
      setPollToken((n) => n + 1); // restart the poller to follow the new OCR run
    } catch (err: any) {
      alert('Retry failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSubmitting(false);
    }
  };

  const isOCRRunning = docStatus === 'uploaded' || docStatus === 'processing';
  const isIndexing = docStatus === 'indexing';
  const isOCRReady = docStatus === 'ocr_ready';
  const isIndexed = docStatus === 'indexed';
  const isFailed = docStatus === 'failed';
  const showPanels = reviewData && (isOCRReady || isIndexed || isIndexing);

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Upload Drag & Drop Box */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-soft-sm">
        <h2 className="text-lg font-bold text-slate-900 dark:text-white mb-2">Upload Document for OCR Extraction</h2>
        <p className="text-xs text-slate-500 mb-4">Supported formats: PDF, PNG, JPG, JPEG, TIFF (Max 25MB)</p>

        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (e.dataTransfer.files?.[0]) handleFileUpload(e.dataTransfer.files[0]);
          }}
          className="border-2 border-dashed border-slate-300 dark:border-slate-700 hover:border-brand-500 dark:hover:border-brand-500 rounded-2xl p-8 text-center transition cursor-pointer bg-slate-50/50 dark:bg-slate-800/30"
        >
          <input
            type="file"
            id="fileInput"
            className="hidden"
            accept=".pdf,.png,.jpg,.jpeg,.tiff"
            onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
          />
          <label htmlFor="fileInput" className="cursor-pointer flex flex-col items-center">
            <div className="w-12 h-12 rounded-xl bg-brand-50 dark:bg-brand-950 text-brand-600 dark:text-brand-400 flex items-center justify-center mb-3">
              <Upload className="w-6 h-6" />
            </div>
            <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
              Click to upload or drag &amp; drop file scan
            </p>
            <p className="text-xs text-slate-400 mt-1">PaddleOCR executes multi-block text &amp; layout extraction</p>
          </label>
        </div>

        {uploadState.isUploading && (
          <div className="mt-4 p-4 rounded-xl bg-brand-50 dark:bg-brand-950/50 border border-brand-200 dark:border-brand-800">
            <div className="flex justify-between text-xs font-semibold text-brand-700 dark:text-brand-300 mb-1">
              <span className="flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Uploading file…
              </span>
              <span>{uploadState.uploadProgress}%</span>
            </div>
            <div className="w-full bg-brand-200 dark:bg-brand-900 rounded-full h-2 overflow-hidden">
              <div
                className="bg-brand-600 h-2 rounded-full transition-all duration-300"
                style={{ width: `${uploadState.uploadProgress}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Status + Review Panel */}
      {docId && (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-soft-sm space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-brand-500" />
                <h3 className="font-bold text-slate-900 dark:text-white text-base">
                  {reviewData?.filename || 'Document OCR Review'}
                </h3>
              </div>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <span className="text-xs text-slate-500">Status:</span>
                {docStatus === null && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-slate-100 dark:bg-slate-800 text-slate-500 flex items-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin" /> Checking…
                  </span>
                )}
                {isOCRRunning && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-300 border border-amber-200 dark:border-amber-800 flex items-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {STAGE_LABEL[docStatus!]}
                  </span>
                )}
                {isOCRReady && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                    ✓ OCR Ready — Review &amp; Confirm
                  </span>
                )}
                {isIndexing && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 flex items-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {STAGE_LABEL.indexing}
                  </span>
                )}
                {isIndexed && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                    ✓ Indexed — {chunkCount} chunks searchable
                  </span>
                )}
                {isFailed && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-300 border border-rose-200 dark:border-rose-800 flex items-center gap-1.5">
                    <AlertCircle className="w-3 h-3" /> Failed
                  </span>
                )}
              </div>
            </div>

            {/* Mobile Tab Switcher */}
            <div className="flex sm:hidden border border-slate-200 dark:border-slate-800 rounded-xl p-1 bg-slate-100 dark:bg-slate-800">
              <button
                onClick={() => setMobileTab('text')}
                className={`flex-1 py-1 text-xs font-semibold rounded-lg ${
                  mobileTab === 'text' ? 'bg-white dark:bg-slate-900 text-brand-600 shadow-sm' : 'text-slate-500'
                }`}
              >
                Extracted Text
              </button>
              <button
                onClick={() => setMobileTab('original')}
                className={`flex-1 py-1 text-xs font-semibold rounded-lg ${
                  mobileTab === 'original' ? 'bg-white dark:bg-slate-900 text-brand-600 shadow-sm' : 'text-slate-500'
                }`}
              >
                Original Blocks
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => loadReviewData(docId)}
                disabled={isOCRRunning || isIndexing}
                className="p-2 border border-slate-200 dark:border-slate-700 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs font-semibold disabled:opacity-40"
                title="Refresh OCR Data"
              >
                <RefreshCw className="w-4 h-4" />
              </button>

              {isFailed && (
                <button
                  onClick={handleRetry}
                  disabled={submitting}
                  className="px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-60 text-white font-semibold rounded-xl text-xs shadow-soft-sm flex items-center gap-2 transition"
                >
                  <RotateCcw className="w-4 h-4" /> Retry Extraction
                </button>
              )}

              {(isOCRReady || isIndexed) && (
                <button
                  onClick={handleConfirmAndIndex}
                  disabled={submitting || loadingReview || !editedText.trim()}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-60 text-white font-semibold rounded-xl text-xs shadow-soft-sm flex items-center gap-2 transition"
                >
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <CheckCircle className="w-4 h-4" />}
                  <span>{isIndexed ? 'Re-index with edits' : 'Confirm & Index for Chat'}</span>
                </button>
              )}

              {isIndexed && (
                <button
                  onClick={() => navigate(`/chat?doc=${docId}`)}
                  className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white font-semibold rounded-xl text-xs shadow-soft-sm flex items-center gap-2 transition"
                >
                  💬 Chat with Document
                </button>
              )}
            </div>
          </div>

          {statusError && (
            <div className="p-3 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-xs text-rose-700 dark:text-rose-300 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{statusError}</span>
            </div>
          )}

          {(isOCRRunning || isIndexing) && (
            <div className="flex flex-col items-center justify-center py-16 space-y-4">
              <div className="relative">
                <div className="w-16 h-16 rounded-full border-4 border-slate-200 dark:border-slate-800"></div>
                <div className="w-16 h-16 rounded-full border-4 border-t-brand-500 border-r-transparent border-b-transparent border-l-transparent absolute top-0 left-0 animate-spin"></div>
              </div>
              <div className="text-center">
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                  {STAGE_LABEL[docStatus!]}
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  This page updates itself — large scanned PDFs can take a few minutes.
                </p>
              </div>
            </div>
          )}

          {loadingReview && !isOCRRunning && !isIndexing && (
            <p className="py-12 text-center text-slate-400 text-sm flex items-center justify-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading extracted blocks…
            </p>
          )}

          {showPanels && !loadingReview && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left Pane: Extracted Blocks */}
              <div className={`space-y-4 ${mobileTab === 'original' ? 'block' : 'hidden lg:block'}`}>
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                    <Eye className="w-4 h-4 text-brand-500" /> Extracted Layout Blocks
                  </h4>
                  <span className="text-xs bg-brand-50 dark:bg-brand-950 text-brand-600 dark:text-brand-300 px-2 py-0.5 rounded-full font-semibold">
                    {reviewData.blocks?.length || 0} blocks · {reviewData.total_pages} page(s)
                  </span>
                </div>

                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800 max-h-[500px] overflow-y-auto space-y-3">
                  {reviewData.blocks && reviewData.blocks.length > 0 ? (
                    reviewData.blocks.map((block) => (
                      <div
                        key={block.block_id}
                        className="p-3 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 text-xs shadow-soft-sm space-y-1"
                      >
                        <div className="flex items-center justify-between text-slate-400 gap-2">
                          <span className="font-bold text-brand-500">
                            Block #{block.block_id}
                            {block.page ? ` · Page ${block.page}` : ''}
                          </span>
                          <span className="flex items-center gap-1.5">
                            {block.source && (
                              <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-500 rounded-md">
                                {block.source === 'paddleocr' ? 'OCR' : 'text layer'}
                              </span>
                            )}
                            {typeof block.confidence === 'number' && (
                              <span className="px-2 py-0.5 bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-300 font-semibold rounded-md">
                                {(block.confidence * 100).toFixed(0)}%
                              </span>
                            )}
                          </span>
                        </div>
                        <p className="text-slate-800 dark:text-slate-200 font-medium whitespace-pre-wrap">{block.text}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-slate-400 text-center py-4">No blocks extracted.</p>
                  )}
                </div>
              </div>

              {/* Right Pane: Editable Text */}
              <div className={`space-y-4 ${mobileTab === 'text' ? 'block' : 'hidden lg:block'}`}>
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                    <Edit3 className="w-4 h-4 text-emerald-500" /> Editable Extracted Text
                  </h4>
                  <span className="text-xs text-slate-400">
                    {editedText.split(/\s+/).filter(Boolean).length} words
                  </span>
                </div>

                <textarea
                  value={editedText}
                  onChange={(e) => setEditedText(e.target.value)}
                  rows={18}
                  disabled={isIndexing}
                  className="w-full p-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl font-mono text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500 transition leading-relaxed disabled:opacity-60"
                  placeholder="Review and edit OCR extracted text here…"
                />
                <p className="text-xs text-slate-400">
                  Corrections here are what gets chunked and embedded. Editing an indexed
                  document and re-indexing replaces its old chunks.
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
