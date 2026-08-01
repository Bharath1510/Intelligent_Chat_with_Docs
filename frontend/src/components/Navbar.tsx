import React from 'react';
import { useTheme } from '../context/ThemeContext';
import { Sun, Moon, Sparkles, Github } from 'lucide-react';

const REPO_URL = 'https://github.com/Bharath1510/Intelligent_Chat_with_Docs';

export const Navbar: React.FC = () => {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="h-16 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md sticky top-0 z-40 px-6 flex items-center justify-between transition-colors">
      <div className="flex items-center space-x-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-400 flex items-center justify-center text-white shadow-soft-sm">
          <Sparkles className="w-5 h-5" />
        </div>
        <div>
          <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-brand-600 to-indigo-500 bg-clip-text text-transparent">
            DocuBrain AI
          </span>
          <span className="ml-2 text-xs font-semibold px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-900/50 text-brand-600 dark:text-brand-300 border border-brand-200 dark:border-brand-700">
            OCR + RAG
          </span>
        </div>
      </div>

      <div className="flex items-center space-x-3">
        {/* Dark / Light Mode Toggle */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition"
          title="Toggle Theme"
        >
          {theme === 'dark' ? <Sun className="w-5 h-5 text-amber-400" /> : <Moon className="w-5 h-5 text-slate-600" />}
        </button>

        {/* Source repository */}
        <div className="hidden sm:flex items-center space-x-2 pl-3 border-l border-slate-200 dark:border-slate-800">
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            title="View the source on GitHub"
            className="px-3 py-1.5 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 rounded-full text-xs font-semibold border border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700 hover:text-slate-900 dark:hover:text-white transition flex items-center gap-1.5"
          >
            <Github className="w-3.5 h-3.5" />
            GitHub
          </a>
        </div>
      </div>
    </header>
  );
};
