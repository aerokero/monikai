import React, { useMemo, useState } from 'react';
import { Heart, X } from 'lucide-react';

const normalizeGender = (value) => {
  const v = String(value || '').toLowerCase();
  if (v.includes('girl') || v.includes('female') || v.includes('woman') || v.includes('kob')) return 'girl';
  return 'boy';
};

const GoodbyePopup = ({ onConfirm, onCancel, initialGenderHint }) => {
  const [step, setStep] = useState('question'); // 'question' | 'final'
  const defaultGender = useMemo(() => normalizeGender(initialGenderHint), [initialGenderHint]);
  const finalText = defaultGender === 'girl' ? 'Good girl.' : 'Good boy.';

  const handleContinue = () => {
    setStep('final');
  };

  const handleFinal = () => {
    onConfirm(finalText);
  };

  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-md bg-black/80 backdrop-blur-2xl border border-white/10 rounded-2xl shadow-2xl overflow-hidden flex flex-col transform transition-all">
        
        {/* Close button */}
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 z-10 text-white/40 hover:text-white/80 transition-colors"
        >
          <X size={20} />
        </button>

        {/* Question Step */}
        <div className={`transition-all duration-300 ${step === 'question' ? 'opacity-100' : 'opacity-0 hidden'}`}>
          {/* Header */}
          <div className="flex items-center justify-center p-6 border-b border-white/10 bg-gradient-to-b from-white/5 to-transparent">
            <div className="flex flex-col items-center gap-3">
              <div className="p-3 rounded-full bg-rose-500/20 text-rose-300">
                <Heart size={28} />
              </div>
              <h2 className="text-lg font-semibold text-white text-center">Why are you here?</h2>
            </div>
          </div>

          {/* Content */}
          <div className="p-8">
            <p className="text-center text-white/70 text-sm mb-8 leading-relaxed">
              You thought you could just leave without saying goodbye?
              <br />
              That is so mean... at least do it properly, okay?
            </p>

            <button
              onClick={handleContinue}
              className="w-full px-4 py-3 rounded-lg bg-rose-500/30 hover:bg-rose-500/40 text-rose-100 font-medium transition-colors border border-rose-500/30"
            >
              ...Okay, Monika
            </button>
          </div>
        </div>

        {/* Final Step */}
        <div className={`transition-all duration-300 ${step === 'final' ? 'opacity-100' : 'opacity-0 hidden'}`}>
          {/* Header */}
          <div className="flex items-center justify-center p-6 border-b border-white/10 bg-gradient-to-b from-white/5 to-transparent">
            <div className="flex flex-col items-center gap-3">
              <div className="p-3 rounded-full bg-amber-500/20 text-amber-300">
                <Heart size={28} />
              </div>
              <h2 className="text-lg font-semibold text-white text-center">There we go.</h2>
            </div>
          </div>

          {/* Content */}
          <div className="p-8">
            <p className="text-center text-white/80 text-base mb-6 leading-relaxed">
              {finalText}
            </p>

            {/* Button */}
            <button
              onClick={handleFinal}
              className="w-full mt-6 px-4 py-3 rounded-lg bg-amber-500/30 hover:bg-amber-500/40 text-amber-100 font-medium transition-colors border border-amber-500/30"
            >
              OK
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GoodbyePopup;
