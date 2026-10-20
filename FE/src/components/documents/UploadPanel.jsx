import { CloudUpload, FileText, ScanText, X } from "lucide-react";
import { useRef, useState } from "react";
import { documentsApi } from "../../api/services";
import { useToast } from "../../context/ToastContext";
import { ACCEPTED_FILES, CATEGORIES, CATEGORY_KEYS } from "../../lib/constants";
import { classNames, formatBytes } from "../../lib/format";
import { Button, Field, Input, ProgressBar, Select } from "../ui/primitives";

export default function UploadPanel({ dealId, onUploaded }) {
  const toast = useToast();
  const inputRef = useRef(null);
  const [files, setFiles] = useState([]);
  const [category, setCategory] = useState("financial");
  const [description, setDescription] = useState("");
  const [dragging, setDragging] = useState(false);
  const [progress, setProgress] = useState(null);

  const addFiles = (list) => {
    const incoming = Array.from(list || []);
    setFiles((current) => {
      const names = new Set(current.map((f) => f.name + f.size));
      return [...current, ...incoming.filter((f) => !names.has(f.name + f.size))];
    });
  };

  const upload = async () => {
    if (!files.length) return;
    setProgress(0);
    try {
      const result = await documentsApi.upload(dealId, files, category, description.trim(), setProgress);
      if (result.uploaded.length) {
        toast.success(`${result.uploaded.length} document(s) uploaded. Processing has started.`, "Upload complete");
      }
      result.skipped.forEach((skip) => toast.warning(`${skip.filename}: ${skip.reason}`, "Skipped"));
      setFiles([]);
      setDescription("");
      onUploaded?.(result);
    } catch (error) {
      toast.error(error, "Upload failed");
    } finally {
      setProgress(null);
    }
  };

  return (
    <div className="upload-panel">
      <div
        className={classNames("dropzone", dragging && "dragging")}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
      >
        <input ref={inputRef} type="file" multiple accept={ACCEPTED_FILES} hidden onChange={(e) => addFiles(e.target.files)} />
        <span className="dropzone-icon">
          <CloudUpload size={26} />
        </span>
        <strong>Drop files here or click to browse</strong>
        <p>PDF, Word, Excel, CSV, text and images · up to 50 MB each</p>
        <span className="dropzone-ocr">
          <ScanText size={13} /> Scanned PDFs and images are OCR'd automatically
        </span>
      </div>

      {files.length > 0 && (
        <div className="upload-queue">
          <ul>
            {files.map((file) => (
              <li key={file.name + file.size}>
                <FileText size={15} />
                <span className="truncate">{file.name}</span>
                <small>{formatBytes(file.size)}</small>
                {progress === null && (
                  <button className="icon-btn ghost sm" onClick={() => setFiles(files.filter((f) => f !== file))} aria-label="Remove file">
                    <X size={13} />
                  </button>
                )}
              </li>
            ))}
          </ul>
          <div className="upload-options">
            <Field label="Workstream / category">
              <Select value={category} onChange={(e) => setCategory(e.target.value)} options={CATEGORY_KEYS.map((key) => ({ value: key, label: CATEGORIES[key].label }))} />
            </Field>
            <Field label="Note (optional)">
              <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="e.g. Provided by seller on 12 Oct" maxLength={2000} />
            </Field>
          </div>
          {progress !== null && <ProgressBar value={progress} />}
          <div className="upload-actions">
            <Button variant="secondary" onClick={() => setFiles([])} disabled={progress !== null}>
              Clear
            </Button>
            <Button icon={CloudUpload} onClick={upload} loading={progress !== null}>
              {progress !== null ? `Uploading ${progress}%` : `Upload ${files.length} file${files.length > 1 ? "s" : ""}`}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
