import React from "react";

import './Header.css'

export default function Header({ onReset, hasJob }) {
  return (
    <header className="header">
      <div className="header__inner">
        <div className="header__brand">
          <span className="header__logo">⬡</span>
          <span className="header__name">IntelliDoc</span>
          <span className="header__tag">OCR Pipeline</span>
        </div>
        {hasJob && (
          <button className="header__new" onClick={onReset}>
            + New Document
          </button>
        )}
      </div>
    </header>
  )
}
