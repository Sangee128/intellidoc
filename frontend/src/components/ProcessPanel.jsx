import React from "react";

import { useEffect, useRef } from 'react'
import './ProcessPanel.css'

const STAGES = [
  'Loading image',
  'Layout detection',
  'Full-page OCR',
  'Extracting blocks',
  'Building reading order',
  'Saving overlay image',
  'Generating DOCX',
  'Done',
]

export default function ProcessPanel({ jobId, job, onJobUpdate, onDone }) {
  const pollRef = useRef(null)

  useEffect(() => {
    const poll = async () => {
      try {
        const res  = await fetch(`/api/jobs/${jobId}`)
        const data = await res.json()
        onJobUpdate(data)

        if (data.status === 'done') {
          clearInterval(pollRef.current)
          // Fetch full result JSON
          const rRes  = await fetch(`/api/json/${jobId}`)
          const rData = await rRes.json()
          onDone(data, rData)
        } else if (data.status === 'error') {
          clearInterval(pollRef.current)
        }
      } catch (e) {
        console.error('Poll error:', e)
      }
    }

    pollRef.current = setInterval(poll, 800)
    poll()
    return () => clearInterval(pollRef.current)
  }, [jobId])

  const progress = job?.progress ?? 0
  const stage    = job?.stage    ?? 'Starting…'
  const isError  = job?.status   === 'error'

  return (
    <div className="process-wrap">
      <div className="process-card">
        <div className="process-card__header">
          <div className="process-spinner">
            {isError
              ? <span className="process-spinner__err">✕</span>
              : <span className="spinner process-spinner__anim" />}
          </div>
          <div>
            <h2 className="process-card__title">
              {isError ? 'Processing failed' : 'Processing document'}
            </h2>
            <p className="process-card__file">{job?.filename}</p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="process-bar-track">
          <div
            className={`process-bar-fill ${isError ? 'process-bar-fill--err' : ''}`}
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="process-meta">
          <span className="process-stage">{isError ? '⚠ ' + (job?.error?.split('\n')[0] ?? 'Error') : stage}</span>
          <span className="process-pct">{progress}%</span>
        </div>

        {/* Stage checklist */}
        <div className="process-stages">
          {STAGES.map((s, i) => {
            const idx = STAGES.findIndex(st => stage.startsWith(st.split(' ')[0]))
            let state = 'pending'
            if (i < idx || progress === 100) state = 'done'
            else if (i === idx) state = 'active'
            return (
              <div key={s} className={`process-stage-row process-stage-row--${state}`}>
                <span className="process-stage-row__dot" />
                <span>{s}</span>
              </div>
            )
          })}
        </div>

        {isError && (
          <details className="process-error">
            <summary>Show error details</summary>
            <pre>{job?.error}</pre>
          </details>
        )}
      </div>
    </div>
  )
}
