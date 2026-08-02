import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Send,
  Share2,
  ZoomIn,
  ZoomOut,
} from '../icons';
import { getDocument, GlobalWorkerOptions } from 'pdfjs-dist/legacy/build/pdf.mjs';
import workerSrc from 'pdfjs-dist/legacy/build/pdf.worker.mjs?url';
import NoteWorkspace from '../NoteWorkspace';
import ShellPanelFrame from '../shared/ShellPanelFrame';
import useElementSize from '../../hooks/useElementSize';
import { useLanguage } from '../../contexts/LanguageContext';

GlobalWorkerOptions.workerSrc = workerSrc;

const clampZoom = (value) => Math.max(0.6, Math.min(value, 2.4));

const prettifyTitle = (name) => {
  const base = String(name || '')
    .replace(/\.pdf$/i, '')
    .replace(/[_]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return base
    .replace(/\s+-\s+(\d+(st|nd|rd|th)\s+Edition)$/i, ' ($1)')
    .replace(/\s+Answer\s+Key$/i, ' (Answer Key)');
};

const StudyShellPanel = ({
  socket,
  catalog,
  selection,
  onSelectStudy,
  onRefreshCatalog,
  shareRef,
}) => {
  const { t } = useLanguage();
  const [selectedFolder, setSelectedFolder] = useState(selection?.folder || '');
  const [selectedFile, setSelectedFile] = useState(selection?.file || '');
  const [fields, setFields] = useState([]);
  const [fieldsTitle, setFieldsTitle] = useState('');
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [scratchText, setScratchText] = useState('');
  const [scratchPath, setScratchPath] = useState('');
  const [renderEpoch, setRenderEpoch] = useState(0);
  const [pageLabels, setPageLabels] = useState(null);
  const [outlineItems, setOutlineItems] = useState([]);
  const [chapterJump, setChapterJump] = useState('');
  const [pageInput, setPageInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [shareNotice, setShareNotice] = useState('');
  const [showSpinner, setShowSpinner] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [isPanning, setIsPanning] = useState(false);

  const [panelRef, panelSize] = useElementSize();
  const [viewerMeasureRef, viewerSize] = useElementSize();

  const viewerRef = useRef(null);
  const pageCanvasRef = useRef(null);
  const aiCanvasRef = useRef(null);
  const renderTaskRef = useRef(null);
  const pdfDocRef = useRef(null);
  const lastSentRef = useRef({ page: 0, ts: 0 });
  const pageTextCacheRef = useRef({});
  const renderSeqRef = useRef(0);
  const lastRenderedPageRef = useRef(0);
  const syncTimerRef = useRef(null);
  const suppressEmitRef = useRef(false);
  const docLoadTaskRef = useRef(null);
  const spinnerTimerRef = useRef(null);
  const spinnerStartRef = useRef(0);
  const shareNoticeTimerRef = useRef(null);
  const lastImageSentRef = useRef({ page: 0, ts: 0 });
  const lastHiResPageRef = useRef(0);
  const panStateRef = useRef({ active: false, startX: 0, startY: 0, scrollLeft: 0, scrollTop: 0 });

  const scratchBase = useMemo(() => 'study/shared', []);
  const defaultScratchPath = `${scratchBase}/scratchpad.md`;
  const folders = Array.isArray(catalog?.folders) ? catalog.folders : [];
  const activeFolder = folders.find((folder) => folder.name === selectedFolder) || folders[0] || null;
  const visibleFiles = activeFolder ? (activeFolder.files || []).filter((file) => !file.is_answer_key) : [];
  const activeFile = useMemo(() => {
    if (!activeFolder) return null;
    const exact = (activeFolder.files || []).find((file) => file.name === selectedFile);
    if (exact && !exact.is_answer_key) return exact;
    return visibleFiles[0] || null;
  }, [activeFolder, selectedFile, visibleFiles]);
  const pageLabel = pageLabels && pageLabels[page - 1] ? String(pageLabels[page - 1]) : '';
  const hasDocument = Boolean(activeFile?.path && pageCount > 0 && !loadError);
  const isWide = panelSize.width >= 1180;
  const isCompact = panelSize.width > 0 && panelSize.width < 760;
  const notesShellWidth = isWide ? Math.max(360, Math.floor(panelSize.width * 0.32)) : Math.max(0, panelSize.width - 48);

  useEffect(() => {
    if (selection?.folder) setSelectedFolder(selection.folder);
    if (selection?.file) setSelectedFile(selection.file);
  }, [selection?.file, selection?.folder]);

  useEffect(() => {
    if (!selectedFolder && activeFolder) {
      setSelectedFolder(activeFolder.name);
    }
  }, [activeFolder, selectedFolder]);

  useEffect(() => {
    if (activeFile && (activeFile.name !== selectedFile || activeFolder?.name !== selectedFolder)) {
      const folderName = activeFolder?.name || selectedFolder || '';
      setSelectedFolder(folderName);
      setSelectedFile(activeFile.name);
      setPage(1);
      setPageCount(0);
      pdfDocRef.current = null;
      setPageLabels(null);
      setOutlineItems([]);
      setLoadError('');
      setZoom(1);
      pageTextCacheRef.current = {};
      if (onSelectStudy) {
        onSelectStudy({
          folder: folderName,
          file: activeFile.name,
          path: activeFile.path,
        });
      }
    }
  }, [activeFile, activeFolder, onSelectStudy, selectedFile, selectedFolder]);

  const startSpinner = useCallback(() => {
    spinnerStartRef.current = Date.now();
    if (spinnerTimerRef.current) {
      clearTimeout(spinnerTimerRef.current);
      spinnerTimerRef.current = null;
    }
    setShowSpinner(true);
  }, []);

  const stopSpinner = useCallback(() => {
    const elapsed = Date.now() - spinnerStartRef.current;
    const delay = elapsed < 420 ? 420 - elapsed : 0;
    if (spinnerTimerRef.current) {
      clearTimeout(spinnerTimerRef.current);
    }
    spinnerTimerRef.current = setTimeout(() => {
      setShowSpinner(false);
      spinnerTimerRef.current = null;
    }, delay);
  }, []);

  const buildOutlineItems = useCallback(async (doc) => {
    if (!doc?.getOutline) return [];
    try {
      const outline = await doc.getOutline();
      if (!Array.isArray(outline) || outline.length === 0) return [];
      const items = [];
      const walk = async (nodes, depth = 0) => {
        for (const node of nodes) {
          const titleRaw = String(node?.title || '').trim();
          let pageIndex = null;
          try {
            let dest = node?.dest;
            if (typeof dest === 'string') {
              dest = await doc.getDestination(dest);
            }
            if (Array.isArray(dest) && dest[0] !== undefined && dest[0] !== null) {
              pageIndex = typeof dest[0] === 'number' ? dest[0] : await doc.getPageIndex(dest[0]);
            }
          } catch {
            pageIndex = null;
          }
          if (Number.isFinite(pageIndex)) {
            const indent = depth > 0 ? `${'-'.repeat(Math.min(depth, 3))} ` : '';
            items.push({
              title: `${indent}${titleRaw || t('study.section_fallback', { index: pageIndex + 1 })}`.trim(),
              page: pageIndex + 1,
            });
          }
          if (Array.isArray(node?.items) && node.items.length) {
            await walk(node.items, depth + 1);
          }
        }
      };
      await walk(outline, 0);
      return items;
    } catch {
      return [];
    }
  }, [t]);

  useEffect(() => {
    if (!socket) return undefined;
    const onFields = (payload) => {
      const incoming = Array.isArray(payload?.fields) ? payload.fields : [];
      setFieldsTitle(String(payload?.title || ''));
      setFields(
        incoming.map((field, index) => ({
          id: field.key || `f_${index}_${Date.now()}`,
          key: field.key || `field_${index + 1}`,
          label: field.label || field.key || t('study.field_fallback', { index: index + 1 }),
          type: field.type === 'textarea' ? 'textarea' : 'text',
          placeholder: field.placeholder || '',
          value: field.value || '',
        }))
      );
    };

    const onNotes = (payload) => {
      const text = String(payload?.text || '');
      const mode = payload?.mode === 'append' ? 'append' : 'replace';
      const idxRaw = payload?.page_index;
      const targetIndex = Number.isFinite(idxRaw) ? Math.max(0, Number(idxRaw)) : null;
      const targetPath = targetIndex !== null
        ? `${scratchBase}/page-${targetIndex + 1}.md`
        : (scratchPath || `${scratchBase}/scratchpad.md`);

      if (targetIndex !== null) {
        setScratchPath(targetPath);
      }

      socket.emit(mode === 'append' ? 'memory_append_page' : 'memory_set_page', { path: targetPath, content: text });
      socket.emit('memory_get_page', { path: targetPath });
      socket.emit('memory_list_pages');
    };

    const onPage = (payload) => {
      const next = Number(payload?.page || 1);
      if (Number.isFinite(next) && next > 0) {
        suppressEmitRef.current = true;
        setPage(next);
      }
    };

    socket.on('study_fields', onFields);
    socket.on('study_notes', onNotes);
    socket.on('study_page', onPage);

    return () => {
      socket.off('study_fields', onFields);
      socket.off('study_notes', onNotes);
      socket.off('study_page', onPage);
    };
  }, [scratchBase, scratchPath, socket, t]);

  useEffect(() => {
    if (!activeFile?.path) {
      setIsLoading(false);
      setLoadError('');
      if (spinnerTimerRef.current) {
        clearTimeout(spinnerTimerRef.current);
        spinnerTimerRef.current = null;
      }
      setShowSpinner(false);
      return undefined;
    }

    setIsLoading(true);
    setLoadError('');
    startSpinner();

    const backendBase = import.meta.env?.DEV ? '' : 'http://localhost:8000';
    const url = `${backendBase}/study/file?path=${encodeURIComponent(activeFile.path)}`;
    let cancelled = false;

    const loadFromDoc = (doc) => {
      if (cancelled) return;
      pdfDocRef.current = doc;
      setPageCount(doc.numPages || 0);
      lastSentRef.current = { page: 0, ts: 0 };
      setRenderEpoch((current) => current + 1);
      setIsLoading(false);
      stopSpinner();
      doc.getPageLabels().then((labels) => {
        if (!cancelled) {
          setPageLabels(Array.isArray(labels) && labels.length ? labels : null);
        }
      }).catch(() => {
        if (!cancelled) setPageLabels(null);
      });
      buildOutlineItems(doc).then((items) => {
        if (!cancelled) setOutlineItems(items);
      }).catch(() => {
        if (!cancelled) setOutlineItems([]);
      });
    };

    const task = getDocument({
      url,
      disableRange: true,
      disableStream: true,
      disableAutoFetch: true,
    });
    docLoadTaskRef.current = task;

    task.promise.then((doc) => {
      loadFromDoc(doc);
    }).catch(async () => {
      if (cancelled) return;
      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const buffer = await response.arrayBuffer();
        const fallbackTask = getDocument({ data: new Uint8Array(buffer) });
        docLoadTaskRef.current = fallbackTask;
        loadFromDoc(await fallbackTask.promise);
      } catch (error) {
        if (!cancelled) {
          console.error('Failed to load PDF', error);
          pdfDocRef.current = null;
          setPageCount(0);
          setOutlineItems([]);
          setIsLoading(false);
          stopSpinner();
          setLoadError(error?.message || 'Failed to load PDF');
        }
      }
    });

    return () => {
      cancelled = true;
      try {
        docLoadTaskRef.current?.destroy?.();
      } catch {
        // ignore
      }
    };
  }, [activeFile?.path, buildOutlineItems, startSpinner, stopSpinner]);

  useEffect(() => {
    if (viewerSize.width > 0 && viewerSize.height > 0) {
      setRenderEpoch((current) => current + 1);
    }
  }, [viewerSize.height, viewerSize.width]);

  useEffect(() => {
    setRenderEpoch((current) => current + 1);
  }, [zoom]);

  useEffect(() => {
    if (zoom <= 1 && viewerRef.current) {
      viewerRef.current.scrollLeft = 0;
      viewerRef.current.scrollTop = 0;
    }
  }, [zoom]);

  const emitStudyPageUser = useCallback((pageNumber) => {
    if (!socket || !activeFile?.path || pageNumber <= 0) return;
    const now = Date.now();
    if (lastSentRef.current.page === pageNumber && now - lastSentRef.current.ts < 1500) {
      return;
    }
    lastSentRef.current = { page: pageNumber, ts: now };
    const cached = pageTextCacheRef.current[pageNumber];
    if (cached) {
      socket.emit('study_page_user', {
        folder: selectedFolder,
        file: selectedFile,
        page: pageNumber,
        page_label: pageLabels && pageLabels[pageNumber - 1] ? String(pageLabels[pageNumber - 1]) : '',
        text: cached,
      });
      return;
    }

    const doc = pdfDocRef.current;
    if (!doc) {
      socket.emit('study_page_user', {
        folder: selectedFolder,
        file: selectedFile,
        page: pageNumber,
        page_label: pageLabels && pageLabels[pageNumber - 1] ? String(pageLabels[pageNumber - 1]) : '',
      });
      return;
    }

    doc.getPage(pageNumber).then((pdfPage) => pdfPage.getTextContent()).then((content) => {
      const text = (content?.items || []).map((item) => item.str).join(' ');
      const cleaned = text.replace(/\s+/g, ' ').trim();
      const clipped = cleaned.length > 2000 ? cleaned.slice(0, 2000) : cleaned;
      pageTextCacheRef.current[pageNumber] = clipped;
      socket.emit('study_page_user', {
        folder: selectedFolder,
        file: selectedFile,
        page: pageNumber,
        page_label: pageLabels && pageLabels[pageNumber - 1] ? String(pageLabels[pageNumber - 1]) : '',
        text: clipped,
      });
    }).catch(() => {
      socket.emit('study_page_user', {
        folder: selectedFolder,
        file: selectedFile,
        page: pageNumber,
        page_label: pageLabels && pageLabels[pageNumber - 1] ? String(pageLabels[pageNumber - 1]) : '',
      });
    });
  }, [activeFile?.path, pageLabels, selectedFile, selectedFolder, socket]);

  const emitStudyPageImage = useCallback((pageNumber) => {
    if (!socket || !selectedFile) return;
    const canvas = pageCanvasRef.current;
    if (!canvas || lastRenderedPageRef.current !== pageNumber) return;
    const now = Date.now();
    const last = lastImageSentRef.current;
    if (last.page === pageNumber && now - last.ts < 1200) return;
    lastImageSentRef.current = { page: pageNumber, ts: now };
    const dataUrl = canvas.toDataURL('image/jpeg', 0.75);
    const base64 = dataUrl.split(',')[1] || '';
    if (!base64) return;
    socket.emit('study_page_image', {
      folder: selectedFolder,
      file: selectedFile,
      page: pageNumber,
      page_label: pageLabels && pageLabels[pageNumber - 1] ? String(pageLabels[pageNumber - 1]) : '',
      mime_type: 'image/jpeg',
      data: base64,
    });
  }, [pageLabels, selectedFile, selectedFolder, socket]);

  const scheduleStudySync = useCallback((pageNumber) => {
    if (!socket || !selectedFile) return;
    if (syncTimerRef.current) {
      clearTimeout(syncTimerRef.current);
    }
    syncTimerRef.current = setTimeout(() => {
      const shouldSendText = !suppressEmitRef.current;
      if (suppressEmitRef.current) {
        suppressEmitRef.current = false;
      }
      emitStudyPageImage(pageNumber);
      if (shouldSendText) {
        emitStudyPageUser(pageNumber);
      }
    }, 450);
  }, [emitStudyPageImage, emitStudyPageUser, selectedFile, socket]);

  const renderPage = useCallback(async (pageNumber) => {
    const doc = pdfDocRef.current;
    const canvas = pageCanvasRef.current;
    if (!doc || !canvas || viewerSize.width <= 0 || viewerSize.height <= 0) return;

    const seq = renderSeqRef.current + 1;
    renderSeqRef.current = seq;

    try {
      const pageObject = await doc.getPage(pageNumber);
      const viewport = pageObject.getViewport({ scale: 1 });
      const targetWidth = Math.max(260, viewerSize.width - 24);
      const targetHeight = Math.max(220, viewerSize.height - 24);
      const baseScale = Math.min(targetWidth / viewport.width, targetHeight / viewport.height);
      const scaledViewport = pageObject.getViewport({ scale: baseScale * zoom });
      const context = canvas.getContext('2d');
      canvas.width = Math.floor(scaledViewport.width);
      canvas.height = Math.floor(scaledViewport.height);
      canvas.style.width = `${Math.floor(scaledViewport.width)}px`;
      canvas.style.height = `${Math.floor(scaledViewport.height)}px`;
      if (renderTaskRef.current?.cancel) {
        try {
          renderTaskRef.current.cancel();
        } catch {
          // ignore
        }
      }
      const task = pageObject.render({ canvasContext: context, viewport: scaledViewport });
      renderTaskRef.current = task;
      await task.promise;
      if (seq !== renderSeqRef.current || pageNumber !== page) return;
      lastRenderedPageRef.current = pageNumber;
      scheduleStudySync(pageNumber);
    } catch {
      // ignore rapid page changes
    }
  }, [page, scheduleStudySync, viewerSize.height, viewerSize.width, zoom]);

  useEffect(() => {
    if (!socket) return undefined;
    const onConnect = () => {
      if (page > 0 && selectedFile) {
        renderPage(page);
      }
    };
    socket.on('connect', onConnect);
    return () => socket.off('connect', onConnect);
  }, [page, renderPage, selectedFile, socket]);

  useEffect(() => {
    if (!pageCount || viewerSize.width <= 0 || viewerSize.height <= 0) return;
    const currentPage = Math.min(pageCount, Math.max(1, page));
    renderPage(currentPage);
  }, [page, pageCount, renderEpoch, renderPage, viewerSize.height, viewerSize.width]);

  useEffect(() => () => {
    if (syncTimerRef.current) {
      clearTimeout(syncTimerRef.current);
    }
    if (shareNoticeTimerRef.current) {
      clearTimeout(shareNoticeTimerRef.current);
    }
    if (spinnerTimerRef.current) {
      clearTimeout(spinnerTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (pageCount > 0 && page > pageCount) {
      setPage(1);
    }
  }, [page, pageCount]);

  const handleWheelZoom = (event) => {
    if (!hasDocument) return;
    event.preventDefault();
    event.stopPropagation();
    const direction = event.deltaY > 0 ? -1 : 1;
    setZoom((current) => clampZoom(current * (direction > 0 ? 1.08 : 0.92)));
  };

  const handlePanStart = (event) => {
    if (!hasDocument || zoom <= 1 || event.button !== 0) return;
    const node = viewerRef.current;
    if (!node) return;
    event.preventDefault();
    panStateRef.current = {
      active: true,
      startX: event.clientX,
      startY: event.clientY,
      scrollLeft: node.scrollLeft,
      scrollTop: node.scrollTop,
    };
    setIsPanning(true);
  };

  const handlePanMove = useCallback((event) => {
    if (!panStateRef.current.active) return;
    const node = viewerRef.current;
    if (!node) return;
    const dx = event.clientX - panStateRef.current.startX;
    const dy = event.clientY - panStateRef.current.startY;
    node.scrollLeft = panStateRef.current.scrollLeft - dx;
    node.scrollTop = panStateRef.current.scrollTop - dy;
  }, []);

  const handlePanEnd = useCallback(() => {
    if (!panStateRef.current.active) return;
    panStateRef.current.active = false;
    setIsPanning(false);
  }, []);

  useEffect(() => {
    if (!isPanning) return undefined;
    window.addEventListener('mousemove', handlePanMove);
    window.addEventListener('mouseup', handlePanEnd);
    window.addEventListener('mouseleave', handlePanEnd);
    return () => {
      window.removeEventListener('mousemove', handlePanMove);
      window.removeEventListener('mouseup', handlePanEnd);
      window.removeEventListener('mouseleave', handlePanEnd);
    };
  }, [handlePanEnd, handlePanMove, isPanning]);

  const updateField = (id, value) => {
    setFields((current) => current.map((field) => (field.id === id ? { ...field, value } : field)));
  };

  const submitAnswers = () => {
    if (!socket) return;
    socket.emit('study_answers_submit', {
      folder: selectedFolder,
      file: selectedFile,
      fields: fields.reduce((acc, field) => {
        acc[field.label || field.key] = field.value || '';
        return acc;
      }, {}),
      notes: scratchText.trim(),
    });
  };

  const handleScratchChange = ({ text = '', path = '' }) => {
    setScratchText(text);
    if (path) setScratchPath(path);
  };

  const changePage = (nextPage) => {
    if (!pageCount) return;
    setPage(Math.min(pageCount, Math.max(1, Number(nextPage) || 1)));
  };

  const resolvePageInput = (raw) => {
    const value = String(raw || '').trim();
    if (!value) return null;
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
    if (Array.isArray(pageLabels) && pageLabels.length) {
      const matchIndex = pageLabels.findIndex((label) => String(label).toLowerCase() === value.toLowerCase());
      if (matchIndex >= 0) return matchIndex + 1;
    }
    return null;
  };

  const applyPageInput = () => {
    const target = resolvePageInput(pageInput);
    if (!target) return;
    changePage(target);
    setPageInput('');
  };

  const ensureHiResPage = async (targetWidthOverride) => {
    const doc = pdfDocRef.current;
    if (!doc) return null;
    let canvas = aiCanvasRef.current;
    if (!canvas || lastHiResPageRef.current !== page) {
      const pdfPage = await doc.getPage(page);
      const viewport = pdfPage.getViewport({ scale: 1 });
      const baseWidth = Math.max(1600, Math.min(3200, viewerSize.width * 3.2));
      const hiResWidth = targetWidthOverride || baseWidth;
      const hiResViewport = pdfPage.getViewport({ scale: hiResWidth / viewport.width });
      canvas = aiCanvasRef.current || document.createElement('canvas');
      aiCanvasRef.current = canvas;
      canvas.width = Math.floor(hiResViewport.width);
      canvas.height = Math.floor(hiResViewport.height);
      await pdfPage.render({ canvasContext: canvas.getContext('2d'), viewport: hiResViewport }).promise;
      lastHiResPageRef.current = page;
    }
    return canvas;
  };

  const shareWithMonika = useCallback(async () => {
    if (!socket || !selectedFile) return;
    try {
      if (shareNoticeTimerRef.current) {
        clearTimeout(shareNoticeTimerRef.current);
      }
      setShareNotice(t('study.sharing_notice'));
      shareNoticeTimerRef.current = setTimeout(() => {
        setShareNotice('');
        shareNoticeTimerRef.current = null;
      }, 2200);
      const canvas = await ensureHiResPage(Math.max(2200, Math.min(3800, viewerSize.width * 4)));
      if (!canvas) return;
      const dataUrl = canvas.toDataURL('image/jpeg', 0.82);
      const base64 = dataUrl.split(',')[1] || '';
      if (!base64) return;
      socket.emit('study_page_share', {
        folder: selectedFolder,
        file: selectedFile,
        page,
        page_label: pageLabel,
        mime_type: 'image/jpeg',
        data: base64,
      });
    } catch {
      // ignore share failures
    }
  }, [page, pageLabel, selectedFile, selectedFolder, socket, t, viewerSize.width]);

  useEffect(() => {
    if (!shareRef) return undefined;
    shareRef.current = shareWithMonika;
    return () => {
      if (shareRef.current === shareWithMonika) {
        shareRef.current = null;
      }
    };
  }, [shareRef, shareWithMonika]);

  const refreshCatalog = () => {
    if (onRefreshCatalog) onRefreshCatalog();
  };

  return (
    <ShellPanelFrame
      icon={BookOpen}
      title={t('study.title')}
      subtitle={activeFile?.name ? prettifyTitle(activeFile.name) : t('study.subtitle_empty')}
      actions={(
        <button
          onClick={refreshCatalog}
          className="inline-flex items-center gap-1.5 rounded-xl border border-white/12 bg-white/[0.06] px-3 py-2 text-xs text-white/78 transition-colors hover:bg-white/[0.11]"
          title={t('study.refresh_catalog')}
        >
          <RefreshCw size={13} />
          {t('study.refresh')}
        </button>
      )}
      bodyClassName="min-h-0"
    >
      <div
        ref={panelRef}
        className={`grid h-full min-h-0 gap-3 overflow-auto p-3 custom-scrollbar ${isWide ? 'grid-cols-[minmax(0,1.55fr)_minmax(330px,0.92fr)]' : 'grid-cols-1 auto-rows-max'}`}
      >
        <section className="flex min-h-[360px] min-w-0 flex-col overflow-hidden rounded-[18px] border border-white/10 bg-black/20">
          <div className="border-b border-white/10 bg-white/[0.04] px-3 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={selectedFolder}
                onChange={(event) => setSelectedFolder(event.target.value)}
                className="min-w-[140px] rounded-xl border border-white/12 bg-black/30 px-3 py-2 text-xs text-white/82 outline-none"
              >
                {folders.map((folder) => (
                  <option key={folder.name} value={folder.name}>{prettifyTitle(folder.name)}</option>
                ))}
              </select>
              <select
                value={selectedFile}
                onChange={(event) => {
                  const name = event.target.value;
                  setSelectedFile(name);
                  const file = visibleFiles.find((entry) => entry.name === name);
                  if (file && onSelectStudy) {
                    onSelectStudy({ folder: selectedFolder, file: file.name, path: file.path });
                  }
                }}
                className="min-w-[160px] flex-1 rounded-xl border border-white/12 bg-black/30 px-3 py-2 text-xs text-white/82 outline-none"
                title={selectedFile}
              >
                {visibleFiles.map((file) => (
                  <option key={file.name} value={file.name}>{prettifyTitle(file.name)}</option>
                ))}
              </select>
              {outlineItems.length > 0 ? (
                <select
                  value={chapterJump}
                  onChange={(event) => {
                    const target = Number(event.target.value);
                    if (Number.isFinite(target) && target > 0) {
                      changePage(target);
                    }
                    setChapterJump('');
                  }}
                  className="min-w-[150px] rounded-xl border border-white/12 bg-black/30 px-3 py-2 text-xs text-white/82 outline-none"
                >
                  <option value="">{t('study.chapters')}</option>
                  {outlineItems.map((item, index) => (
                    <option key={`${item.page}-${index}`} value={item.page}>
                      {item.title} · p. {item.page}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>

            <div className={`mt-3 flex flex-wrap items-center gap-2 ${isCompact ? '' : 'justify-between'}`}>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => changePage(page - 1)}
                  disabled={page <= 1}
                  className="rounded-xl border border-white/10 bg-white/[0.05] px-2.5 py-2 text-white/72 transition-colors hover:bg-white/[0.1] disabled:cursor-not-allowed disabled:opacity-35"
                  title={t('study.previous_page')}
                >
                  <ChevronLeft size={14} />
                </button>
                <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-black/25 px-2.5 py-1.5 text-[11px] text-white/65">
                  <input
                    value={pageInput}
                    onChange={(event) => setPageInput(event.target.value)}
                    onBlur={applyPageInput}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        applyPageInput();
                      }
                    }}
                    placeholder={t('study.go_to_page')}
                    className="w-16 bg-transparent outline-none"
                  />
                  <span className="text-white/28">|</span>
                  <span>{pageCount > 0 ? `${page}/${pageCount}` : page}</span>
                  {pageLabel ? <span className="text-white/45">{t('study.book_page_label', { label: pageLabel })}</span> : null}
                </div>
                <button
                  onClick={() => changePage(page + 1)}
                  disabled={pageCount > 0 ? page >= pageCount : false}
                  className="rounded-xl border border-white/10 bg-white/[0.05] px-2.5 py-2 text-white/72 transition-colors hover:bg-white/[0.1] disabled:cursor-not-allowed disabled:opacity-35"
                  title={t('study.next_page')}
                >
                  <ChevronRight size={14} />
                </button>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => setZoom((current) => clampZoom(current - 0.12))}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.05] px-3 py-2 text-xs text-white/78 transition-colors hover:bg-white/[0.1]"
                >
                  <ZoomOut size={13} />
                  {t('study.zoom_out')}
                </button>
                <button
                  onClick={() => setZoom(1)}
                  className="rounded-xl border border-white/10 bg-black/25 px-3 py-2 text-xs text-white/72"
                >
                  {Math.round(zoom * 100)}%
                </button>
                <button
                  onClick={() => setZoom((current) => clampZoom(current + 0.12))}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.05] px-3 py-2 text-xs text-white/78 transition-colors hover:bg-white/[0.1]"
                >
                  <ZoomIn size={13} />
                  {t('study.zoom_in')}
                </button>
                <button
                  onClick={shareWithMonika}
                  disabled={!hasDocument}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-xs text-cyan-100 transition-colors hover:bg-cyan-400/16 disabled:cursor-not-allowed disabled:opacity-45"
                >
                  <Share2 size={13} />
                  {t('study.share')}
                </button>
              </div>
            </div>
          </div>

          <div className="relative flex-1 min-h-[300px] bg-black/45">
            <div ref={viewerMeasureRef} className="absolute inset-0">
              {hasDocument ? (
                <div
                  ref={viewerRef}
                  className={`flex h-full w-full items-center justify-center overflow-auto p-3 scrollbar-hide ${zoom > 1 ? (isPanning ? 'cursor-grabbing' : 'cursor-grab') : 'cursor-default'}`}
                  onMouseDown={handlePanStart}
                >
                  <canvas
                    ref={pageCanvasRef}
                    className="rounded bg-white shadow-[0_12px_28px_rgba(0,0,0,0.45)]"
                    onWheel={handleWheelZoom}
                  />
                </div>
              ) : (
                <div className="flex h-full items-center justify-center px-6 text-center text-sm text-white/42">
                  {loadError ? t('study.load_failed', { error: loadError }) : (isLoading ? t('study.loading_document') : t('study.no_file_selected'))}
                </div>
              )}
            </div>

            {shareNotice ? (
              <div className="absolute left-1/2 top-4 z-10 -translate-x-1/2 rounded-full border border-white/12 bg-black/72 px-3 py-1.5 text-xs text-white/85 shadow-lg">
                {shareNotice}
              </div>
            ) : null}

            {showSpinner ? (
              <div className="absolute inset-0 flex items-center justify-center bg-black/18">
                <div className="h-10 w-10 rounded-full border-2 border-white/20 border-t-white/80 animate-spin" />
              </div>
            ) : null}
          </div>
        </section>

        <div className="flex min-h-0 flex-col gap-3">
          <section className={`${isWide ? 'flex-1 min-h-0' : 'min-h-[320px]'} overflow-hidden rounded-[18px] border border-white/10 bg-black/20`}>
            <NoteWorkspace
              socket={socket}
              defaultPath={defaultScratchPath}
              basePath={scratchBase}
              filterPrefix={scratchBase}
              onContentChange={handleScratchChange}
              compact
              hideCategories
              hidePaths
              shellMode
              shellWidth={notesShellWidth}
              singlePage
              titleOverride={t('study.scratchpad_title')}
            />
          </section>

          <section className="overflow-hidden rounded-[18px] border border-white/10 bg-black/20">
            <div className="border-b border-white/10 px-3 py-2.5">
              <div className="text-[11px] uppercase tracking-[0.2em] text-white/45">
                {fieldsTitle || t('study.tasks_answers')}
              </div>
            </div>

            <div className="space-y-3 p-3">
              {fields.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] px-4 py-5 text-sm text-white/38">
                  {t('study.fields_empty')}
                </div>
              ) : (
                fields.map((field) => (
                  <label key={field.id} className="flex flex-col gap-1.5">
                    <span className="text-[11px] text-white/58">{field.label}</span>
                    {field.type === 'textarea' ? (
                      <textarea
                        value={field.value}
                        onChange={(event) => updateField(field.id, event.target.value)}
                        placeholder={field.placeholder}
                        className="min-h-[92px] w-full rounded-2xl border border-white/10 bg-black/28 px-3 py-2 text-sm text-white/82 outline-none"
                      />
                    ) : (
                      <input
                        value={field.value}
                        onChange={(event) => updateField(field.id, event.target.value)}
                        placeholder={field.placeholder}
                        className="w-full rounded-2xl border border-white/10 bg-black/28 px-3 py-2 text-sm text-white/82 outline-none"
                      />
                    )}
                  </label>
                ))
              )}
            </div>

            {fields.length > 0 ? (
              <div className="border-t border-white/10 p-3">
                <button
                  onClick={submitAnswers}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-white/12 bg-white/[0.08] px-4 py-3 text-sm text-white/88 transition-colors hover:bg-white/[0.14]"
                >
                  <Send size={15} />
                  {t('study.submit_answers')}
                </button>
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </ShellPanelFrame>
  );
};

export default StudyShellPanel;
