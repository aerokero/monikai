import React from 'react';
import { X, Bell, AlertCircle } from 'lucide-react';

const ToastStack = ({ toasts = [], onDismiss = () => {} }) => {
  return (
    <div className="fixed top-16 right-4 z-[100] flex flex-col gap-3 pointer-events-none">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="pointer-events-auto w-80 bg-black/60 backdrop-blur-2xl border border-white/10 rounded-xl shadow-2xl overflow-hidden animate-in slide-in-from-right-5 fade-in duration-300"
        >
          <div className="p-4 flex gap-3">
            <div className="shrink-0 mt-0.5">
              {toast.variant === 'error' ? (
                <div className="w-8 h-8 rounded-full bg-red-500/10 flex items-center justify-center text-red-400 border border-red-500/20">
                  <AlertCircle size={16} />
                </div>
              ) : (
                <div className="w-8 h-8 rounded-full bg-white/10 flex items-center justify-center text-white border border-white/20">
                  <Bell size={16} />
                </div>
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-white/90 leading-relaxed break-words">
                {toast.text}
              </p>
            </div>
            <button
              onClick={() => onDismiss(toast.id)}
              className="shrink-0 -mt-1 -mr-1 p-1.5 text-white/30 hover:text-white hover:bg-white/10 rounded-lg transition-colors h-fit"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

export default ToastStack;
