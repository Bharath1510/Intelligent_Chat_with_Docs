import React from 'react';
import { DocProcessingStatus } from '../types';

const STYLES: Record<DocProcessingStatus, string> = {
  uploaded:
    'bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-200 dark:border-slate-700',
  processing:
    'bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-300 border-amber-200 dark:border-amber-800',
  ocr_ready:
    'bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-800',
  indexing:
    'bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800',
  indexed:
    'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800',
  failed:
    'bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-300 border-rose-200 dark:border-rose-800',
};

const LABELS: Record<DocProcessingStatus, string> = {
  uploaded: 'Queued',
  processing: 'Running OCR',
  ocr_ready: 'Needs review',
  indexing: 'Indexing',
  indexed: 'Indexed',
  failed: 'Failed',
};

export const StatusBadge: React.FC<{ status: DocProcessingStatus; title?: string | null }> = ({
  status,
  title,
}) => (
  <span
    title={title || LABELS[status] || status}
    className={`text-xs px-2.5 py-0.5 rounded-full font-semibold border whitespace-nowrap ${
      STYLES[status] || STYLES.uploaded
    }`}
  >
    {LABELS[status] || status}
  </span>
);
