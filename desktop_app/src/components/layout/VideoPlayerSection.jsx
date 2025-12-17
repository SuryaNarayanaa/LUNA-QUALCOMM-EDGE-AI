import { useState, useRef, useEffect } from "react"
import { motion } from "framer-motion"

export default function VideoUpload({ onVideoUpload, uploadedVideo, fileName, audioUrl, onTimeUpdate, onDuration }) {
    const [dragActive, setDragActive] = useState(false)
    const [uploading, setUploading] = useState(false)
    const inputRef = useRef(null)
    const videoRef = useRef(null)
    const audioRef = useRef(null)

    // Improved sync for custom audio
    useEffect(() => {
        if (!audioUrl || !videoRef.current || !audioRef.current) return;
        const video = videoRef.current;
        const audio = audioRef.current;

        // When a new audio track arrives, pause both and reset to start so nothing auto-plays.
        video.pause();
        audio.pause();
        video.currentTime = 0;
        audio.currentTime = 0;

        const syncPlay = () => {
            audio.currentTime = video.currentTime;
            audio.play();
        };
        const syncPause = () => { audio.pause(); };
        const syncTime = () => {
            if (Math.abs(audio.currentTime - video.currentTime) > 0.1) {
                audio.currentTime = video.currentTime;
            }
        };
        const syncSeeked = () => {
            audio.currentTime = video.currentTime;
        };
        video.addEventListener('play', syncPlay);
        video.addEventListener('pause', syncPause);
        video.addEventListener('timeupdate', syncTime);
        video.addEventListener('seeked', syncSeeked);
        // Cleanup
        return () => {
            video.removeEventListener('play', syncPlay);
            video.removeEventListener('pause', syncPause);
            video.removeEventListener('timeupdate', syncTime);
            video.removeEventListener('seeked', syncSeeked);
        };
    }, [audioUrl]);

    const handleDrag = (e) => {
        e.preventDefault()
        e.stopPropagation()
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true)
        } else if (e.type === "dragleave") {
            setDragActive(false)
        }
    }

    const handleDrop = (e) => {
        e.preventDefault()
        e.stopPropagation()
        setDragActive(false)
        const files = e.dataTransfer.files
        if (files.length > 0) {
            handleFile(files[0])
        }
    }

    const handleChange = (e) => {
        const file = e.target.files[0]
        if (file) {
            handleFile(file)
        }
    }

    const onButtonClick = () => {
        inputRef.current.click()
    }

    const handleFile = (file) => {
        if (file.type.startsWith("video/")) {
            setUploading(true)
            
            // Simulate upload delay
            setTimeout(() => {
                const videoUrl = URL.createObjectURL(file)
                onVideoUpload(file,videoUrl)
                setUploading(false)
            }, 1000)
        } else {
            alert("Please upload a video file")
        }
    }

    useEffect(() => {
        if (!videoRef.current) return;
        const video = videoRef.current;

        const handleTimeUpdate = () => {
            if (onTimeUpdate) onTimeUpdate(video.currentTime || 0);
        };
        const handleLoaded = () => {
            if (onDuration) onDuration(video.duration || 0);
        };
        video.addEventListener('timeupdate', handleTimeUpdate);
        video.addEventListener('loadedmetadata', handleLoaded);
        return () => {
            video.removeEventListener('timeupdate', handleTimeUpdate);
            video.removeEventListener('loadedmetadata', handleLoaded);
        };
    }, [onTimeUpdate, onDuration]);

    return (
        <div className="w-full h-full bg-zinc-900 rounded-lg">
            {!uploadedVideo ? (
                <div
                    className={`relative border-2 border-dashed rounded-lg p-8 text-center transition-colors h-full
                        ${dragActive 
                            ? "border-blue-400 bg-zinc-800/50" 
                            : "border-zinc-700 hover:border-zinc-600"
                        }`}
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                >
                    <input ref={inputRef} type="file" accept="video/*" onChange={handleChange} className="hidden" />

                    {uploading ? (
                        <div className="py-12">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
                            <p className="text-zinc-400">Uploading {fileName}...</p>
                        </div>
                    ) : (
                        <div className="py-12">
                            <svg
                                className="mx-auto h-12 w-12 text-zinc-600 mb-4"
                                stroke="currentColor"
                                fill="none"
                                viewBox="0 0 48 48"
                            >
                                <path
                                    d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                                    strokeWidth={2}
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                />
                            </svg>
                            <h3 className="text-lg font-medium text-zinc-200 mb-2">Upload your video</h3>
                            <p className="text-zinc-400 mb-4">Drag and drop your video file here, or click to browse</p>
                            <button
                                onClick={onButtonClick}
                                className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-md transition-colors"
                            >
                                Choose File
                            </button>
                            <p className="text-xs text-zinc-500 mt-2">Supports MP4, MOV, AVI, and other video formats</p>
                        </div>
                    )}
                </div>
            ) : (
                <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="space-y-4 h-full"
                >
                    <div className="bg-zinc-800 rounded-lg p-4 h-full">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-lg font-medium text-zinc-200">Video Preview</h3>
                            <button 
                                onClick={() => onVideoUpload(null, "")} 
                                className="text-zinc-400 hover:text-zinc-200 text-sm"
                            >
                                Upload New
                            </button>
                        </div>
                        <div style={{ position: 'relative' }}>
                            <video 
                                ref={videoRef}
                                src={uploadedVideo} 
                                controls 
                                muted={!!audioUrl} // Always mute video if custom audio is present
                                className="w-full rounded-md bg-black" 
                                style={{ maxHeight: "calc(100vh - 200px)" }}
                            >
                                Your browser does not support the video tag.
                            </video>
                            {audioUrl && (
                                <audio
                                    key={audioUrl}
                                    ref={audioRef}
                                    src={audioUrl}
                                    controls={false} // Hide controls for end user
                                    muted={false} // Ensure audio is not muted
                                    style={{ display: 'none' }} // Hide audio element
                                />
                            )}
                        </div>
                        <p className="text-sm text-zinc-400 mt-2">{fileName}</p>
                    </div>
                </motion.div>
            )}
        </div>
    )
}