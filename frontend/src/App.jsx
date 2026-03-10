import React from "react";
import { useState, useCallback } from 'react'
import UploadZone   from './components/UploadZone.jsx'
import ProcessPanel from './components/ProcessPanel.jsx'
import ResultPanel  from './components/ResultPanel.jsx'
import Header       from './components/Header.jsx'
import './App.css'

export default function App() {
  const [jobId,  setJobId]  = useState(null)
  const [job,    setJob]    = useState(null)
  const [result, setResult] = useState(null)  // full JSON result

  const handleUploaded = useCallback((id) => {
    setJobId(id)
    setJob({ id, status: 'queued', progress: 0, stage: 'Queued' })
    setResult(null)
  }, [])

  const handleDone = useCallback((jobData, resultData) => {
    setJob(jobData)
    setResult(resultData)
  }, [])

  const handleReset = useCallback(() => {
    if (jobId) {
      fetch(`/api/jobs/${jobId}`, { method: 'DELETE' }).catch(() => {})
    }
    setJobId(null)
    setJob(null)
    setResult(null)
  }, [jobId])

  return (
    <div className="app">
      <Header onReset={handleReset} hasJob={!!jobId} />

      <main className="app__main">
        {!jobId && (
          <UploadZone onUploaded={handleUploaded} />
        )}

        {jobId && !result && (
          <ProcessPanel
            jobId={jobId}
            job={job}
            onJobUpdate={setJob}
            onDone={handleDone}
          />
        )}

        {result && (
          <ResultPanel
            jobId={jobId}
            result={result}
            filename={job?.filename}
            onReset={handleReset}
          />
        )}
      </main>
    </div>
  )
}
