import { motion } from "framer-motion";
import { useRef, useState } from "react";

const MotionDiv = motion.div;

function UploadBox({ onUpload, uploading, uploadProgress }) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef(null);

  const handleFiles = (files) => {
    const file = files?.[0];
    if (!file) {
      return;
    }
    onUpload(file);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    setDragActive(false);
    handleFiles(event.dataTransfer.files);
  };

  return (
    <MotionDiv
      whileHover={{ scale: 1.01 }}
      onDragOver={(event) => {
        event.preventDefault();
        setDragActive(true);
      }}
      onDragLeave={() => setDragActive(false)}
      onDrop={handleDrop}
      className={`rounded-2xl border-2 border-dashed bg-white p-4 transition-all ${
        dragActive ? "border-blue-400 shadow-md" : "border-slate-200"
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(event) => handleFiles(event.target.files)}
        disabled={uploading}
      />

      <p className="text-sm font-semibold text-slate-800">Upload PDF</p>
      <p className="mt-1 text-xs text-slate-500">Drag and drop here or click to browse</p>

      <button
        type="button"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
        className="mt-4 w-full rounded-xl bg-blue-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {uploading ? "Processing document..." : "Select PDF"}
      </button>

      {uploading && (
        <div className="mt-3">
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <MotionDiv
              initial={{ width: 0 }}
              animate={{ width: `${uploadProgress}%` }}
              className="h-full rounded-full bg-blue-500"
            />
          </div>
          <p className="mt-1 text-right text-xs text-slate-500">{uploadProgress}%</p>
        </div>
      )}
    </MotionDiv>
  );
}

export default UploadBox;
