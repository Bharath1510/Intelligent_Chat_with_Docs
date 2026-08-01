import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { api } from '../services/api';
import { useApp } from '../context/AppContext';
import { Upload, FileText, CheckCircle, RefreshCw, Edit3, Eye, Loader2, AlertCircle } from 'lucide-react';

type DocProcessingStatus = 'uploaded' | 'processing' | 'ocr_ready' | 'indexed' | 'failed';

export const UploadReviewPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const selectedDocId = searchParams.get('doc');
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
  const [confirming, setConfirming] = useState(false);
  const [docStatus, setDocStatus] = useState<DocProcessingStatus | null>(null);
  const [mobileTab, setMobileTab] = useState<'original' | 'text'>('text');

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load review data when doc ID changes (from URL or after upload)
  useEffect(() => {
    if (selectedDocId && selectedDocId !== activeReviewDocId) {
      setActiveReviewDocId(selectedDocId);
      startPollingStatus(selectedDocId);
    }
    return () => stopPolling();
  }, [selectedDocId]);

  // Restore review state if coming back to the same doc
  useEffect(() => {
    if (selectedDocId && selectedDocId === activeReviewDocId && reviewData) {
      setDocStatus(reviewData.status as DocProcessingStatus);
    }
  }, [selectedDocId, activeReviewDocId, reviewData]);

  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  };

  const startPollingStatus = (docId: string) => {
    stopPolling();
    // Immediately check status
    checkStatusAndLoad(docId);
    // Then poll every 2s
    pollingRef.current = setInterval(() => checkStatusAndLoad(docId), 2000);
  };

  const checkStatusAndLoad = async (docId: string) => {
    try {
      const res = await api.get(`/documents/${docId}/status`);
      const status = res.data.status as DocProcessingStatus;
      setDocStatus(status);

      if (status === 'ocr_ready' || status === 'indexed') {
        stopPolling();
        loadReviewData(docId);
      } else if (status === 'failed') {
        stopPolling();
      }
      // For 'uploaded' or 'processing', keep polling
    } catch (err) {
      console.error('Failed to check doc status', err);
    }
  };

  const loadReviewData = async (docId: string) => {
    setLoadingReview(true);
    try {
      const res = await api.get(`/documents/${docId}/review`);
      setReviewData(res.data);
      setDocStatus(res.data.status as DocProcessingStatus);
      // Only set edited text if it's a new doc or text was empty
      if (!editedText || activeReviewDocId !== docId) {
        setEditedText(res.data.ocr_edited_text || res.data.ocr_raw_text || '');
      }
    } catch (err) {
      console.error('Failed to fetch review data', err);
    } finally {
      setLoadingReview(false);
    }
  };

  const handleFileUpload = async (file: File) => {
    setUploadState({ isUploading: true, uploadProgress: 10, uploadedDocId: null });

    const formData = new FormData();
    formData.append('file', file);

    try {
      // Simulate progress during actual upload
      const progressInterval = setInterval(() => {
        setUploadState((prev) => ({
          ...prev,
          uploadProgress: Math.min(prev.uploadProgress + 12, 90),
        }));
      }, 300);

      const res = await api.post('/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      clearInterval(progressInterval);
      const newDocId = res.data.document_id;

      setUploadState({ isUploading: false, uploadProgress: 100, uploadedDocId: newDocId });

      // Reset review state for the new document
      setReviewData(null);
      setEditedText('');
      setActiveReviewDocId(newDocId);

      // Navigate to review mode with the new doc ID
      navigate(`/upload?doc=${newDocId}`, { replace: true });
      fetchDocuments();
    } catch (err: any) {
      setUploadState({ isUploading: false, uploadProgress: 0, uploadedDocId: null });
      alert(err.response?.data?.detail || 'File upload failed');
    }
  };

  const handleConfirmAndIndex = async () => {
    if (!reviewData) return;
    setConfirming(true);
    setDocStatus('processing');

    try {
      await api.put(`/documents/${reviewData.id}/confirm`, {
        edited_text: editedText,
      });

      // Poll for indexing completion instead of immediately navigating
      const indexPoll = setInterval(async () => {
        try {
          const res = await api.get(`/documents/${reviewData.id}/status`);
          const status = res.data.status as DocProcessingStatus;
          setDocStatus(status);

          if (status === 'indexed') {
            clearInterval(indexPoll);
            setConfirming(false);
            fetchDocuments();
            // Update review data status locally
            setReviewData((prev) => prev ? { ...prev, status: 'indexed' } : null);
          } else if (status === 'failed') {
            clearInterval(indexPoll);
            setConfirming(false);
            alert('Indexing failed. Please try again.');
          }
        } catch (e) {
          console.error('Index status check failed', e);
        }
      }, 1500);

      // Safety timeout — stop polling after 60s
      setTimeout(() => {
        clearInterval(indexPoll);
        setConfirming(false);
      }, 60000);
    } catch (err: any) {
      setConfirming(false);
      setDocStatus('ocr_ready');
      alert('Confirmation failed: ' + (err.response?.data?.detail || err.message));
    }
  };

  const isProcessing = docStatus === 'uploaded' || docStatus === 'processing';
  const isOCRReady = docStatus === 'ocr_ready';
  const isIndexed = docStatus === 'indexed';
  const isFailed = docStatus === 'failed';

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
              Click to upload or drag & drop file scan
            </p>
            <p className="text-xs text-slate-400 mt-1">PaddleOCR executes multi-block text & layout extraction</p>
          </label>
        </div>

        {/* Upload Progress */}
        {uploadState.isUploading && (
          <div className="mt-4 p-4 rounded-xl bg-brand-50 dark:bg-brand-950/50 border border-brand-200 dark:border-brand-800">
            <div className="flex justify-between text-xs font-semibold text-brand-700 dark:text-brand-300 mb-1">
              <span className="flex items-center gap-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Uploading file...
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
      {selectedDocId && (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-soft-sm space-y-4">
          {/* Header with status and actions */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-brand-500" />
                <h3 className="font-bold text-slate-900 dark:text-white text-base">
                  {reviewData?.filename || 'Document OCR Review'}
                </h3>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-xs text-slate-500">Status:</span>
                {isProcessing && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-300 border border-amber-200 dark:border-amber-800 flex items-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {docStatus === 'uploaded' ? 'Queued for OCR...' : 'Running PaddleOCR...'}
                  </span>
                )}
                {isOCRReady && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                    ✓ OCR Ready — Review & Confirm
                  </span>
                )}
                {confirming && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 flex items-center gap-1.5">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Indexing into vector store...
                  </span>
                )}
                {isIndexed && !confirming && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                    ✓ Indexed — Ready for Chat
                  </span>
                )}
                {isFailed && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-300 border border-rose-200 dark:border-rose-800 flex items-center gap-1.5">
                    <AlertCircle className="w-3 h-3" />
                    Failed
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
                onClick={() => loadReviewData(selectedDocId)}
                disabled={isProcessing}
                className="p-2 border border-slate-200 dark:border-slate-700 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs font-semibold disabled:opacity-40"
                title="Refresh OCR Data"
              >
                <RefreshCw className="w-4 h-4" />
              </button>

              {isOCRReady && (
                <button
                  onClick={handleConfirmAndIndex}
                  disabled={confirming || loadingReview}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-60 text-white font-semibold rounded-xl text-xs shadow-soft-sm flex items-center gap-2 transition"
                >
                  {confirming ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Indexing...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle className="w-4 h-4" />
                      <span>Confirm & Index for Chat</span>
                    </>
                  )}
                </button>
              )}

              {isIndexed && !confirming && (
                <button
                  onClick={() => navigate(`/chat?doc=${selectedDocId}`)}
                  className="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white font-semibold rounded-xl text-xs shadow-soft-sm flex items-center gap-2 transition"
                >
                  💬 Chat with Document
                </button>
              )}
            </div>
          </div>

          {/* Processing spinner */}
          {isProcessing && (
            <div className="flex flex-col items-center justify-center py-16 space-y-4">
              <div className="relative">
                <div className="w-16 h-16 rounded-full border-4 border-slate-200 dark:border-slate-800"></div>
                <div className="w-16 h-16 rounded-full border-4 border-t-brand-500 border-r-transparent border-b-transparent border-l-transparent absolute top-0 left-0 animate-spin"></div>
              </div>
              <div className="text-center">
                <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                  {docStatus === 'uploaded' ? 'Queued — Waiting for OCR Engine...' : 'PaddleOCR is extracting text blocks...'}
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  This usually takes 5-15 seconds. The page will auto-update when ready.
                </p>
              </div>
            </div>
          )}

          {/* Loading review data */}
          {loadingReview && !isProcessing && (
            <p className="py-12 text-center text-slate-400 text-sm flex items-center justify-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading extracted blocks...
            </p>
          )}

          {/* Review Panels — only show when OCR is ready or indexed */}
          {!isProcessing && !loadingReview && reviewData && (isOCRReady || isIndexed || confirming) && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left Pane: Original Bounding Blocks */}
              <div
                className={`space-y-4 ${
                  mobileTab === 'original' ? 'block' : 'hidden lg:block'
                }`}
              >
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                    <Eye className="w-4 h-4 text-brand-500" /> Extracted Layout Blocks (PaddleOCR)
                  </h4>
                  <span className="text-xs bg-brand-50 dark:bg-brand-950 text-brand-600 dark:text-brand-300 px-2 py-0.5 rounded-full font-semibold">
                    {reviewData.blocks?.length || 0} Text Blocks
                  </span>
                </div>

                <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-xl border border-slate-200 dark:border-slate-800 max-h-[500px] overflow-y-auto space-y-3">
                  {reviewData.blocks && reviewData.blocks.length > 0 ? (
                    reviewData.blocks.map((block) => (
                      <div
                        key={block.block_id}
                        className="p-3 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 text-xs shadow-soft-sm space-y-1"
                      >
                        <div className="flex items-center justify-between text-slate-400">
                          <span className="font-bold text-brand-500">Block #{block.block_id}</span>
                          <span className="px-2 py-0.5 bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-300 font-semibold rounded-md">
                            Confidence: {(block.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <p className="text-slate-800 dark:text-slate-200 font-medium">{block.text}</p>
                      </div>
                    ))
                  ) : (
                    <p className="text-xs text-slate-400 text-center py-4">No blocks extracted yet.</p>
                  )}
                </div>
              </div>

              {/* Right Pane: Editable Extracted Text */}
              <div
                className={`space-y-4 ${
                  mobileTab === 'text' ? 'block' : 'hidden lg:block'
                }`}
              >
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                    <Edit3 className="w-4 h-4 text-emerald-500" /> Editable Extracted Text (Verify before indexing)
                  </h4>
                  <span className="text-xs text-slate-400">
                    {editedText.split(/\s+/).filter(Boolean).length} words
                  </span>
                </div>

                <textarea
                  value={editedText}
                  onChange={(e) => setEditedText(e.target.value)}
                  rows={18}
                  disabled={isIndexed && !confirming}
                  className="w-full p-4 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl font-mono text-sm text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500 transition leading-relaxed disabled:opacity-60"
                  placeholder="Review and edit OCR extracted text here..."
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
