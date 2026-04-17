import React, { useState } from 'react';
import { Monitor, X, Minus } from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const ScreenWindow = ({ 
    imageSrc, 
    onClose, 
    position
}) => {
    const { t } = useLanguage();
    const [isMinimized, setIsMinimized] = useState(false);
    const usesCustomPosition = Boolean(position && typeof position.x === 'number' && typeof position.y === 'number');

    return (
        <div
            id="screen"
            className="absolute flex flex-col transition-[box-shadow,border-color] duration-200 backdrop-blur-2xl bg-black/50 border border-white/[0.14] shadow-2xl overflow-hidden rounded-xl"
            style={{
                left: usesCustomPosition ? position.x : 'auto',
                top: usesCustomPosition ? position.y : 'auto',
                right: usesCustomPosition ? 'auto' : '16px',
                bottom: usesCustomPosition ? 'auto' : '272px',
                transform: usesCustomPosition ? 'translate(-50%, -50%)' : 'none',
                width: '360px',
                height: isMinimized ? 'auto' : '240px',
                pointerEvents: 'auto',
                zIndex: 40
            }}
        >
            {/* Header */}
            <div 
                className="flex items-center justify-between p-3 border-b border-white/10 bg-white/5 shrink-0"
            >
                <div className="flex items-center gap-2">
                    <Monitor size={16} className="text-white" />
                    <span className="text-xs font-medium tracking-wider text-white/90 uppercase">{t('tools.screen_capture')}</span>
                </div>
                <div className="flex items-center gap-1">
                    <button onClick={() => setIsMinimized(!isMinimized)} className="p-1 hover:bg-white/10 rounded text-white/50 hover:text-white transition-colors">
                        <Minus size={14} />
                    </button>
                    <button onClick={onClose} className="p-1 hover:bg-red-500/20 hover:text-red-400 rounded text-white/50 transition-colors">
                        <X size={14} />
                    </button>
                </div>
            </div>

            {/* Content */}
            <div className="relative flex-1 bg-black overflow-hidden flex items-center justify-center" style={{ display: isMinimized ? 'none' : 'flex', height: isMinimized ? 0 : 'auto' }}>
                {imageSrc ? (
                    <img
                      src={`data:${imageSrc.mime_type || 'image/jpeg'};base64,${imageSrc.data}`}
                      className="w-full h-full object-cover"
                      alt="SCREEN"
                    />
                ) : (
                    <div className="flex flex-col items-center gap-2 text-white/30">
                        <div className="w-8 h-8 border-2 border-white/10 border-t-cyan-500 rounded-full animate-spin" />
                        <span className="text-[10px] tracking-widest uppercase">Waiting for signal...</span>
                    </div>
                )}
            </div>
        </div>
    );
};
export default ScreenWindow;