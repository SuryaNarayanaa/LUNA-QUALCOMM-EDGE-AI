import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Edit3, Check, X, MessageSquare, Clock, Loader } from 'lucide-react';

const VideoTranscriptEditor = ({ 
  transcription,
  segments: initialSegments,
  isLoading,
  onTranscriptEdit,
  onAudioGenerated, // <-- new prop for parent callback
  currentTime: externalCurrentTime = 0,
  duration: externalDuration = 0,
}) => {
  // State for managing segments
  const [transcriptSegments, setTranscriptSegments] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState('');
  const [currentTime, setCurrentTime] = useState(0);
    useEffect(() => {
      setCurrentTime(externalCurrentTime || 0);
    }, [externalCurrentTime]);

  const [selectedSegment, setSelectedSegment] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [requestLipSync, setRequestLipSync] = useState(false);
  
  const scrollContainerRef = useRef(null);
  const activeSegmentRef = useRef(null);

  // Process transcription data when it changes
  useEffect(() => {
    if (transcription?.transcription?.segments) {
      const processedSegments = transcription.transcription.segments.map((seg, i) => ({
        ...seg,
        id: String(i),
        speaker: seg.speaker || 'Speaker 1',
        text: seg.text,
        start: seg.start,
        end: seg.end,
        confidence: seg.confidence || 1,
        isEditable: true
      }));
      setTranscriptSegments(processedSegments);
    } else if (initialSegments) {
      setTranscriptSegments(initialSegments);
    }
  }, [transcription, initialSegments]);

  // Get speaker information
  const getSpeaker = useCallback((speaker) => {
    return {
      name: typeof speaker === 'string' ? speaker : 'Speaker 1',
      color: '#6b7280'
    };
  }, []);

  // Find current active segment based on current time
  const getCurrentSegment = useCallback(() => {
    return transcriptSegments.find(segment => 
      currentTime >= segment.start && currentTime <= segment.end
    );
  }, [transcriptSegments, currentTime]);

  const currentSegment = getCurrentSegment();

  // Auto-scroll to current segment
  useEffect(() => {
    if (currentSegment && activeSegmentRef.current && scrollContainerRef.current) {
      const container = scrollContainerRef.current;
      const element = activeSegmentRef.current;
      
      const containerTop = container.scrollTop;
      const containerBottom = containerTop + container.clientHeight;
      const elementTop = element.offsetTop;
      const elementBottom = elementTop + element.offsetHeight;

      if (elementTop < containerTop || elementBottom > containerBottom) {
        element.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'center'
        });
      }
    }
  }, [currentSegment]);

  // Handle segment selection
  const handleSegmentClick = (segment) => {
    setSelectedSegment(segment);
    setCurrentTime(segment.start);
  };

  // Handle edit start
  const handleEditStart = (segment) => {
    setEditingId(segment.id);
    setEditText(segment.text);
  };

  // Handle edit save
  const handleEditSave = () => {
    if (editingId && editText.trim() !== '') {
      // Update the segment in transcriptSegments
      const updatedSegments = transcriptSegments.map(seg =>
        seg.id === editingId ? { ...seg, text: editText.trim() } : seg
      );
      setTranscriptSegments(updatedSegments);
      // Call the callback with updated segments
      if (onTranscriptEdit) {
        onTranscriptEdit(updatedSegments);
      }
    }
    setEditingId(null);
    setEditText('');
  };

  // Handle edit cancel
  const handleEditCancel = () => {
    setEditingId(null);
    setEditText('');
  };

  // Format time for display
  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // Handle key events for editing
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      handleEditSave();
    } else if (e.key === 'Escape') {
      handleEditCancel();
    }
  };

  // Handler for Update Transcription button
  const handleUpdateTranscription = async () => {
    if (!onTranscriptEdit) return;
    setUpdating(true);
    try {
      const result = await onTranscriptEdit(transcriptSegments, { lipSync: requestLipSync });
      if (result?.audioUrl && onAudioGenerated) {
        onAudioGenerated(result.audioUrl, result);
      }
    } catch (err) {
      alert('Failed to update transcription.');
    } finally {
      setUpdating(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-zinc-900 rounded-lg">
      {/* Header */}
      <div className="p-4 border-b border-zinc-800">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-zinc-200 flex items-center gap-2">
            <MessageSquare className="w-4 h-4" />
            Transcript
          </h3>
          <div className="text-xs text-zinc-500">
            {isLoading ? (
              <div className="flex items-center gap-2">
                <Loader className="w-3 h-3 animate-spin" />
                Processing...
              </div>
            ) : (
              `${transcriptSegments.length} segments`
            )}
          </div>
          
        </div>
        <div className="mt-2 space-y-2">
          <label className="flex items-center gap-2 text-xs text-zinc-300">
            <input
              type="checkbox"
              checked={requestLipSync}
              onChange={(e) => setRequestLipSync(e.target.checked)}
            />
            Also run lip sync
          </label>
          <button
            className="px-4 py-2 rounded bg-blue-600 w-full justify-around text-white hover:bg-blue-700 disabled:opacity-50"
            onClick={handleUpdateTranscription}
            disabled={updating}
          >
            {updating ? 'Updating...' : 'Update Transcription'}
          </button>
        </div>
        
        {/* Current time indicator */}
        <div className="mt-2 flex items-center gap-2 text-xs text-zinc-400">
          <Clock className="w-3 h-3" />
          <span>{formatTime(currentTime)} / {formatTime(externalDuration || 0)}</span>
          {currentSegment && (
            <>
              <span className="text-zinc-500">·</span>
              <div className="flex items-center gap-1">
                <div 
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: getSpeaker(currentSegment.speaker).color }}
                />
                <span className="text-zinc-400">{getSpeaker(currentSegment.speaker).name}</span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex-1 flex flex-col items-center justify-center gap-4">
          <div className="text-center space-y-4">
            <Loader className="w-8 h-8 animate-spin mx-auto text-blue-500" />
            <p className="text-sm text-zinc-400">Processing video transcription...</p>
          </div>
        </div>
      ) : (
        <div ref={scrollContainerRef} className="flex-1 overflow-y-auto p-4 space-y-3">
          <AnimatePresence>
            {transcriptSegments.map((segment) => {
              const speaker = getSpeaker(segment.speaker);
              const isActive = currentSegment?.id === segment.id;
              const isSelected = selectedSegment?.id === segment.id;
              const isEditing = editingId === segment.id;

              return (
                <motion.div
                  key={segment.id}
                  ref={isActive ? activeSegmentRef : null}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className={`group relative p-3 rounded-lg border transition-all duration-200 cursor-pointer ${
                    isActive 
                      ? 'bg-blue-500/10 border-blue-500/30 shadow-lg' 
                      : isSelected
                      ? 'bg-zinc-800/50 border-zinc-700'
                      : 'bg-zinc-900/50 border-zinc-800 hover:bg-zinc-800/30 hover:border-zinc-700'
                  }`}
                  onClick={() => !isEditing && handleSegmentClick(segment)}
                >                {/* Speaker and Time Header */}
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div 
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: speaker.color }}
                      />
                      <div className="flex flex-col">
                        <span className="text-xs font-medium text-zinc-300">
                          {speaker.name}
                        </span>
                        <span className="text-xs text-zinc-500">
                          {formatTime(segment.start)}
                        </span>
                      </div>
                    </div>                  
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-zinc-500">
                        {formatTime(segment.end - segment.start)}s
                      </span>
                      
                      {/* Action buttons */}
                      <div className="flex items-center gap-1">
                        {/* Confidence indicator */}
                        {segment.confidence && (
                          <div className={`w-2 h-2 rounded-full ${
                            segment.confidence > 0.9 
                              ? 'bg-green-500' 
                              : segment.confidence > 0.7 
                              ? 'bg-yellow-500' 
                              : 'bg-red-500'
                          }`} title={`Confidence: ${Math.round(segment.confidence * 100)}%`} />
                        )}
                        
                        {/* Edit button */}
                        {!isEditing && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleEditStart(segment);
                            }}
                            className="opacity-0 group-hover:opacity-100 p-1 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700 rounded transition-all"
                            title="Edit segment"
                          >
                            <Edit3 className="w-3 h-3" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Text Content */}
                  {isEditing ? (
                    <div className="space-y-2">
                      <textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        onKeyDown={handleKeyDown}
                        className="w-full p-2 text-sm bg-zinc-800 border border-zinc-600 rounded resize-none focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        rows={3}
                        autoFocus
                        onClick={(e) => e.stopPropagation()}
                      />
                      
                      {/* Edit Controls */}
                      <div className="flex items-center gap-1">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleEditSave();
                          }}
                          className="p-1 text-green-400 hover:text-green-300 hover:bg-green-400/20 rounded transition-colors"
                          title="Save (Ctrl+Enter)"
                        >
                          <Check className="w-3 h-3" />
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleEditCancel();
                          }}
                          className="p-1 text-red-400 hover:text-red-300 hover:bg-red-400/20 rounded transition-colors"
                          title="Cancel (Esc)"
                        >
                          <X className="w-3 h-3" />
                        </button>
                        <span className="text-xs text-zinc-500 ml-2">
                          Ctrl+Enter to save, Esc to cancel
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className={`text-sm leading-relaxed transition-colors ${
                      isActive 
                        ? 'text-zinc-100' 
                        : 'text-zinc-300'
                    }`}>
                      {segment.text}
                    </p>
                  )  
                }             
                  {isActive && (
                    <motion.div
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      className="absolute -left-1 top-1/2 transform -translate-y-1/2 w-1 h-8 bg-blue-500 rounded-full"
                    />
                  )}
                </motion.div>
              );
            })}
          </AnimatePresence>

          {/* Empty state */}
          {transcriptSegments.length === 0 && (
            <div className="text-center py-12 text-zinc-500">
              <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No transcript segments available</p>
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="p-3 border-t border-zinc-800 bg-zinc-900">
        <div className="text-xs text-zinc-500 space-y-1">
          <div className="text-center">
            Click segments to jump to that time • Auto-scrolls with video
          </div>
          <div className="flex justify-center gap-4 text-zinc-600">
            <span>Ctrl+Enter: Save edit</span>
            <span>Esc: Cancel edit</span>
            <span>Space: Play/Pause</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default VideoTranscriptEditor;
