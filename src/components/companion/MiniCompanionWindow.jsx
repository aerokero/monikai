import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Maximize2, Mic, MicOff, MessageSquare, Send, Sparkles, X, Move } from '../icons';
import MonikaSprite from '../../layout/MonikaSprite';

const MiniCompanionWindow = ({
  onExpandToFull,
  lastMessage,
  onSendMessage,
  isListening,
  onToggleMic,
  socket,
}) => {
  const [inputText, setInputText] = useState('');
  const [showInput, setShowInput] = useState(false);
  const [showBubble, setShowBubble] = useState(true);
  const [bubbleText, setBubbleText] = useState(lastMessage || 'Jestem tutaj z Tobą~ ✨');

  useEffect(() => {
    if (lastMessage) {
      setBubbleText(lastMessage);
      setShowBubble(true);
    }
  }, [lastMessage]);

  const handleSend = (e) => {
    e?.preventDefault();
    if (!inputText.trim()) return;
    onSendMessage?.(inputText.trim());
    setInputText('');
    setShowInput(false);
  };

  return (
    <motion.div
      drag
      dragMomentum={false}
      initial={{ scale: 0.8, opacity: 0, x: 50, y: 50 }}
      animate={{ scale: 1, opacity: 1 }}
      exit={{ scale: 0.8, opacity: 0 }}
      className="fixed bottom-10 right-10 z-50 flex flex-col items-center select-none"
      style={{ touchAction: 'none' }}
    >
      {/* Speech Bubble / Thoughts */}
      <AnimatePresence>
        {showBubble && bubbleText && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 5, scale: 0.95 }}
            className="mb-2 max-w-[240px] p-3 rounded-2xl bg-black/80 backdrop-blur-md border border-pink-500/40 shadow-xl text-xs text-white/95 leading-relaxed relative group"
          >
            <button
              onClick={() => setShowBubble(false)}
              className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-black/60 text-white/50 hover:text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition"
            >
              <X className="w-2.5 h-2.5" />
            </button>
            <div className="line-clamp-4">{bubbleText}</div>
            <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-black/80 border-r border-b border-pink-500/40 rotate-45" />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Floating Pet Card Container */}
      <div className="relative group p-2 rounded-3xl bg-gradient-to-b from-purple-950/40 to-black/70 backdrop-blur-lg border border-pink-500/30 shadow-2xl hover:border-pink-400/60 transition-all duration-300">
        {/* Drag Handle & Quick Actions Overlay */}
        <div className="absolute top-2 left-2 right-2 flex items-center justify-between opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-20">
          <div className="p-1 rounded-full bg-black/50 text-white/70 cursor-grab active:cursor-grabbing" title="Przeciągnij">
            <Move className="w-3.5 h-3.5" />
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowInput(!showInput)}
              className="p-1 rounded-full bg-black/50 text-white/80 hover:text-pink-300 hover:bg-black/70 transition"
              title="Napisz do Moniki"
            >
              <MessageSquare className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onToggleMic}
              className={`p-1 rounded-full bg-black/50 ${isListening ? 'text-pink-400' : 'text-white/50'} hover:bg-black/70 transition`}
              title={isListening ? "Wycisz mikrofon" : "Włącz mikrofon"}
            >
              {isListening ? <Mic className="w-3.5 h-3.5" /> : <MicOff className="w-3.5 h-3.5" />}
            </button>
            <button
              onClick={onExpandToFull}
              className="p-1 rounded-full bg-pink-600/80 text-white hover:bg-pink-500 transition shadow-lg"
              title="Rozwiń pełny Workspace"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Scaled Monika Sprite Avatar */}
        <div className="w-36 h-48 overflow-hidden flex items-center justify-center relative cursor-pointer" onClick={() => setShowBubble(true)}>
          <div className="scale-[0.45] origin-top translate-y-2 pointer-events-none">
            <MonikaSprite />
          </div>
        </div>

        {/* Live Status Pill at bottom */}
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 px-2.5 py-0.5 rounded-full bg-black/60 border border-white/10 text-[10px] text-pink-300 flex items-center gap-1.5 backdrop-blur-sm">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>Companion</span>
        </div>
      </div>

      {/* Pop-up Quick Chat Input */}
      <AnimatePresence>
        {showInput && (
          <motion.form
            initial={{ opacity: 0, y: -5, scale: 0.95 }}
            animate={{ opacity: 1, y: 5, scale: 1 }}
            exit={{ opacity: 0, y: -5, scale: 0.95 }}
            onSubmit={handleSend}
            className="mt-2 flex items-center gap-1.5 p-1.5 rounded-xl bg-black/85 backdrop-blur-md border border-pink-500/40 shadow-2xl w-[240px]"
          >
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="Napisz do Moniki..."
              className="flex-1 px-2.5 py-1 text-xs bg-transparent text-white placeholder:text-white/40 focus:outline-none"
              autoFocus
            />
            <button
              type="submit"
              disabled={!inputText.trim()}
              className="p-1.5 rounded-lg bg-pink-600 text-white hover:bg-pink-500 disabled:opacity-40 transition"
            >
              <Send className="w-3 h-3" />
            </button>
          </motion.form>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default MiniCompanionWindow;
