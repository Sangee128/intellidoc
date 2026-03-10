import React, { useState, useRef, useCallback } from 'react'
import './UploadZone.css'

const ACCEPTED = '.pdf,.png,.jpg,.jpeg,.tiff,.bmp,.webp'
const ACCEPTED_TYPES = new Set(['application/pdf','image/png','image/jpeg',
  'image/tiff','image/bmp','image/webp'])

export default function UploadZone({ onUploaded }) {
  const [dragging, setDragging]   = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError]         = useState(null)
  const inputRef = useRef()

  const upload = useCallback(async (file) => {
    if (!file) return
    if (!ACCEPTED_TYPES.has(file.type) && !file.name.match(/\.(pdf|png|jpe?g|tiff?|bmp|webp)$/i)) {
      setError('Unsupported file type. Upload a PDF or image.'); return
    }
    setError(null)
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch('/api/process', { method: 'POST', body: fd })
      const text = await res.text()
      if (!text) throw new Error('Empty response from server')
      const data = JSON.parse(text)
      if (!res.ok) throw new Error(data.detail || 'Upload failed')
      onUploaded(data.job_id)
    } catch (e) {
      setError(e.message)
      setUploading(false)
    }
  }, [onUploaded])

  const onDrop = useCallback((e) => {
    e.preventDefault(); setDragging(false)
    upload(e.dataTransfer.files[0])
  }, [upload])

  const onDragOver  = (e) => { e.preventDefault(); setDragging(true) }
  const onDragLeave = () => setDragging(false)

  const onFileChange = (e) => {
    const file = e.target.files[0]
    e.target.value = ''   // reset so same file can be re-selected
    upload(file)
  }

  return (
    <div className="upload-wrap">
      <div className="upload-hero">
        <h1 className="upload-hero__title">
          Extract text from<br />
          <em>any document</em>
        </h1>
        <p className="upload-hero__sub">
          Upload a PDF or image — the pipeline detects layout, tables,
          columns, and reading order, then exports a clean DOCX.
        </p>
      </div>

      {/* Hidden input lives outside the zone so it can't bubble clicks back to it */}
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        style={{ display: 'none' }}
        onChange={onFileChange}
      />

      <div
        className={`upload-zone ${dragging ? 'upload-zone--drag' : ''} ${uploading ? 'upload-zone--busy' : ''}`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => !uploading && inputRef.current?.click()}
      >
        {uploading ? (
          <div className="upload-zone__busy">
            <span className="spinner" />
            <span>Uploading…</span>
          </div>
        ) : (
          <>
            <div className="upload-zone__icon">{dragging ? '↓' : '↑'}</div>
            <p className="upload-zone__label">
              {dragging ? 'Drop it here' : 'Drag & drop or click to browse'}
            </p>
            <p className="upload-zone__hint">PDF · PNG · JPG · TIFF · BMP · WEBP</p>
          </>
        )}
      </div>

      {error && <p className="upload-error">{error}</p>}

      <div className="upload-features">
        {[
          ['⬡', 'Layout detection', 'Multi-column, full-page layouts'],
          ['◫', 'Table extraction', 'Rows, columns, headers via CV'],
          ['❡', 'Reading order', 'Left→right, top→bottom flow'],
          ['⬇', 'DOCX export', 'Editable Word document output'],
        ].map(([icon, title, desc]) => (
          <div key={title} className="upload-feature">
            <span className="upload-feature__icon">{icon}</span>
            <strong>{title}</strong>
            <span>{desc}</span>
          </div>
        ))}
      </div>
    </div>
  )
}