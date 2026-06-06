import React, { useState } from 'react';
import { Video, X, Minus } from './icons';
import { useLanguage } from '../contexts/LanguageContext';

const CameraWindow = ({ 
    videoRef, 
    isCameraFlipped, 
    onClose, 
    position
}) => {
    const { t } = useLanguage();
    const [isMinimized, setIsMinimized] = useState(false);
    const usesCustomPosition = Boolean(position && typeof position.x === 'number' && typeof position.y === 'number');

    return (
        <div
            id="video"
            className="absolute flex flex-col transition-[box-shadow,border-color] duration-200 backdrop-blur-2xl bg-black/50 border border-white/[0.14] shadow-2xl overflow-hidden rounded-xl"
            style={{
                left: usesCustomPosition ? position.x : 'auto',
                top: usesCustomPosition ? position.y : 'auto',
                right: usesCustomPosition ? 'auto' : '16px',
                bottom: usesCustomPosition ? 'auto' : '16px',
                transform: usesCustomPosition ? 'translate(-50%, -50%)' : 'none',
                width: '360px',
                height: isMinimized ? 'auto' : '240px',
                pointerEvents: 'auto',
                zIndex: 41
            }}
        >
            {/* Header */}
            <div 
                className="flex items-center justify-between p-3 border-b border-white/10 bg-white/5 shrink-0"
            >
                <div className="flex items-center gap-2">
                    <Video size={16} className="text-white" />
                    <span className="text-xs font-medium tracking-wider text-white/90 uppercase">{t('tools.camera_preview')}</span>
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
            <div className="relative flex-1 bg-black overflow-hidden group" style={{ display: isMinimized ? 'none' : 'block', height: isMinimized ? 0 : 'auto' }}>
                 <video
                  ref={videoRef}
                  autoPlay
                  muted
                  className="absolute inset-0 w-full h-full object-cover"
                  style={{ transform: isCameraFlipped ? 'scaleX(-1)' : 'none' }}
                />
                <div className="absolute top-2 left-2 text-[10px] text-white/50 bg-black/40 px-1.5 rounded border border-white/5 font-mono pointer-events-none">
                  CAM_01
                </div>
            </div>
        </div>
    );
};
export default CameraWindow;
