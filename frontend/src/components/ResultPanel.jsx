import { useState } from 'react'
import './ResultPanel.css'

export default function ResultPanel({ jobId, result, filename, onReset }) {
  const [activeTab, setActiveTab] = useState('content')
  const [overlayLoaded, setOverlayLoaded] = useState(false)

  const blocks  = result?.reading_order ?? []
  const pageSize = result?.page_size
  const cols    = result?.columns_estimate

  const tables  = blocks.filter(b => b.type === 'table')
  const textBlk = blocks.filter(b => b.type !== 'table')

  return (
    <div className="result-wrap">
      {/* Top bar */}
      <div className="result-topbar">
        <div className="result-topbar__info">
          <span className="result-topbar__file">{filename}</span>
          {pageSize && (
            <span className="result-topbar__meta">
              {pageSize.w}×{pageSize.h}px
              {cols ? ` · 2-col (conf ${(cols.conf*100).toFixed(0)}%)` : ' · 1-col'}
              {' · '}{blocks.length} blocks
            </span>
          )}
        </div>
        <div className="result-topbar__actions">
          <a href={`/api/download/${jobId}`} className="btn btn--primary" download>
            ⬇ DOCX
          </a>
          <a href={`/api/download/${jobId}/html`} className="btn btn--secondary" download>
            ⬇ HTML
          </a>
          <a href={`/api/download/${jobId}/md`} className="btn btn--secondary" download>
            ⬇ Markdown
          </a>
          <button className="btn btn--ghost" onClick={onReset}>
            ↩ New document
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="result-tabs">
        {[
          ['content', 'Reading Order'],
          ['overlay', 'Overlay Image'],
          ['raw',     'Raw JSON'],
        ].map(([id, label]) => (
          <button
            key={id}
            className={`result-tab ${activeTab === id ? 'result-tab--active' : ''}`}
            onClick={() => setActiveTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content tab */}
      {activeTab === 'content' && (
        <div className="result-content">
          <div className="result-stats">
            <Stat label="Total blocks" value={blocks.length} />
            <Stat label="Tables"       value={tables.length} />
            <Stat label="Text blocks"  value={textBlk.length} />
            <Stat label="Layout"       value={cols ? '2-column' : '1-column'} />
          </div>

          <div className="result-blocks">
            {blocks.map((unit, i) => (
              <BlockCard key={i} unit={unit} />
            ))}
          </div>
        </div>
      )}

      {/* Overlay tab */}
      {activeTab === 'overlay' && (
        <div className="result-overlay">
          <p className="result-overlay__hint">
            <span className="dot dot--orange">●</span> Full-width &nbsp;
            <span className="dot dot--green">●</span> Left column &nbsp;
            <span className="dot dot--red">●</span> Right column
          </p>
          <div className="result-overlay__frame">
            {!overlayLoaded && <div className="result-overlay__loading"><span className="spinner" /></div>}
            <img
              src={`/api/overlay/${jobId}`}
              alt="Layout overlay"
              onLoad={() => setOverlayLoaded(true)}
              style={{ opacity: overlayLoaded ? 1 : 0 }}
            />
          </div>
        </div>
      )}

      {/* Raw JSON tab */}
      {activeTab === 'raw' && (
        <div className="result-raw">
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div className="result-stat">
      <span className="result-stat__val">{value}</span>
      <span className="result-stat__lbl">{label}</span>
    </div>
  )
}

function BlockCard({ unit }) {
  const type = unit.type || 'text'
  const kind = unit.kind || 'full'
  const order = unit.order

  if (type === 'table') {
    const matrix = unit.table?.matrix ?? []
    const nCols  = Math.max(...matrix.map(r => r.length), 0)
    return (
      <div className={`block-card block-card--table block-card--${kind}`}>
        <div className="block-card__meta">
          <span className="block-tag block-tag--table">table</span>
          <span className="block-kind">{kind}</span>
          <span className="block-order">#{order}</span>
          <span className="block-size">{matrix.length} rows × {nCols} cols</span>
        </div>
        {matrix.length > 0 && nCols > 1 ? (
          <div className="block-table-scroll">
            <table className="block-table">
              <tbody>
                {matrix.map((row, ri) => (
                  <tr key={ri} className={ri < 2 ? 'block-table__hdr' : ''}>
                    {row.map((cell, ci) => (
                      <td key={ci}>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="block-table-fallback">
            {matrix.map((r, i) => <p key={i}>{r[0]}</p>)}
          </div>
        )}
      </div>
    )
  }

  const text = unit.text || ''
  const tagColor = { title: 'title', reference: 'ref', text: 'text', figure: 'fig' }

  return (
    <div className={`block-card block-card--${kind}`}>
      <div className="block-card__meta">
        <span className={`block-tag block-tag--${tagColor[type] ?? 'text'}`}>{type}</span>
        <span className="block-kind">{kind}</span>
        <span className="block-order">#{order}</span>
      </div>
      <p className={`block-text ${type === 'title' ? 'block-text--title' : ''}
                                 ${type === 'reference' ? 'block-text--ref' : ''}`}>
        {text}
      </p>
    </div>
  )
}