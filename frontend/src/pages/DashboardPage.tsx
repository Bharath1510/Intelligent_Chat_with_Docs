import React, { useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useApp } from '../context/AppContext';
import { FileText, MessageSquare, HardDrive, Upload, ArrowRight, CheckCircle2, Clock } from 'lucide-react';

export const DashboardPage: React.FC = () => {
  const { documents, documentsLoading, fetchDocuments } = useApp();
  const navigate = useNavigate();

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const totalIndexed = documents.filter((d) => d.status === 'indexed').length;
  const totalStorageMB = (documents.reduce((acc, d) => acc + d.file_size, 0) / (1024 * 1024)).toFixed(2);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-brand-600 via-indigo-600 to-purple-600 rounded-2xl p-6 text-white shadow-soft-md relative overflow-hidden">
        <div className="relative z-10">
          <h1 className="text-2xl font-bold">Document Intelligence Dashboard</h1>
          <p className="mt-1 text-sm text-brand-100 max-w-xl">
            Extract text with PaddleOCR, correct scans side-by-side, and ask grounded RAG questions with source citations.
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              to="/upload"
              className="px-4 py-2 bg-white text-brand-700 font-semibold rounded-xl text-sm shadow-soft-sm hover:bg-brand-50 transition flex items-center gap-2"
            >
              <Upload className="w-4 h-4" /> Upload Document
            </Link>
            <Link
              to="/chat"
              className="px-4 py-2 bg-brand-700/60 backdrop-blur-md text-white font-semibold rounded-xl text-sm border border-brand-400/40 hover:bg-brand-700 transition flex items-center gap-2"
            >
              <MessageSquare className="w-4 h-4" /> Launch RAG Chat
            </Link>
          </div>
        </div>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-soft-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Total Documents</span>
            <div className="p-2 bg-brand-50 dark:bg-brand-950 rounded-xl text-brand-600 dark:text-brand-400">
              <FileText className="w-5 h-5" />
            </div>
          </div>
          <p className="text-2xl font-bold mt-2 text-slate-900 dark:text-white">{documents.length}</p>
          <span className="text-xs text-emerald-500 font-medium">Ready for indexing</span>
        </div>

        <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-soft-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Indexed for Chat</span>
            <div className="p-2 bg-emerald-50 dark:bg-emerald-950 rounded-xl text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="w-5 h-5" />
            </div>
          </div>
          <p className="text-2xl font-bold mt-2 text-slate-900 dark:text-white">{totalIndexed}</p>
          <span className="text-xs text-slate-400">Vector store chunks active</span>
        </div>

        <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-soft-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">Storage Used</span>
            <div className="p-2 bg-indigo-50 dark:bg-indigo-950 rounded-xl text-indigo-600 dark:text-indigo-400">
              <HardDrive className="w-5 h-5" />
            </div>
          </div>
          <p className="text-2xl font-bold mt-2 text-slate-900 dark:text-white">{totalStorageMB} MB</p>
          <span className="text-xs text-slate-400">PDF / Image upload volume</span>
        </div>

        <div className="bg-white dark:bg-slate-900 p-5 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-soft-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500">OCR Engine</span>
            <div className="p-2 bg-amber-50 dark:bg-amber-950 rounded-xl text-amber-600 dark:text-amber-400">
              <Clock className="w-5 h-5" />
            </div>
          </div>
          <p className="text-2xl font-bold mt-2 text-slate-900 dark:text-white">PaddleOCR</p>
          <span className="text-xs text-emerald-500 font-medium">Ready</span>
        </div>
      </div>

      {/* Recent Documents Table */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-soft-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">Recent Uploaded Scans</h2>
          <Link to="/documents" className="text-xs font-semibold text-brand-600 dark:text-brand-400 hover:underline flex items-center gap-1">
            View All <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {documentsLoading ? (
          <p className="text-sm text-slate-400 py-6 text-center">Loading documents...</p>
        ) : documents.length === 0 ? (
          <div className="text-center py-10 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-xl">
            <Upload className="w-10 h-10 text-slate-400 mx-auto mb-2" />
            <p className="text-sm text-slate-500">No documents uploaded yet.</p>
            <Link to="/upload" className="mt-3 inline-block px-4 py-2 bg-brand-600 text-white text-xs font-semibold rounded-xl">
              Upload Your First Document
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-400 text-xs font-semibold uppercase">
                  <th className="pb-3">Filename</th>
                  <th className="pb-3">Status</th>
                  <th className="pb-3">Size</th>
                  <th className="pb-3">Pages</th>
                  <th className="pb-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {documents.slice(0, 5).map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50 transition">
                    <td className="py-3 font-medium text-slate-900 dark:text-slate-100 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-brand-500" />
                      <span className="truncate max-w-xs">{doc.filename}</span>
                    </td>
                    <td className="py-3">
                      <span
                        className={`text-xs px-2.5 py-1 rounded-full font-semibold capitalize border ${
                          doc.status === 'indexed'
                            ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800'
                            : doc.status === 'ocr_ready'
                            ? 'bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-300 border-blue-200 dark:border-blue-800'
                            : doc.status === 'failed'
                            ? 'bg-rose-50 dark:bg-rose-950/60 text-rose-600 dark:text-rose-300 border-rose-200 dark:border-rose-800'
                            : 'bg-amber-50 dark:bg-amber-950/60 text-amber-600 dark:text-amber-300 border-amber-200 dark:border-amber-800'
                        }`}
                      >
                        {doc.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="py-3 text-slate-500 text-xs">{(doc.file_size / 1024).toFixed(1)} KB</td>
                    <td className="py-3 text-slate-500 text-xs">{doc.total_pages}</td>
                    <td className="py-3 text-right">
                      {doc.status === 'ocr_ready' || doc.status === 'processing' || doc.status === 'uploaded' ? (
                        <button
                          onClick={() => navigate(`/upload?doc=${doc.id}`)}
                          className="px-3 py-1 bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold rounded-lg"
                        >
                          Review OCR
                        </button>
                      ) : doc.status === 'indexed' ? (
                        <button
                          onClick={() => navigate(`/chat?doc=${doc.id}`)}
                          className="px-3 py-1 bg-brand-600 hover:bg-brand-500 text-white text-xs font-semibold rounded-lg"
                        >
                          Chat
                        </button>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
