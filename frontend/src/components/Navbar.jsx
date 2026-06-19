import React from 'react'
import { Link } from 'react-router-dom'

export default function Navbar() {
  return (
    <nav className="navbar">
      <Link to="/" className="navbar-brand">OCR Project</Link>
      <div className="navbar-links">
        <Link to="/">Ana Sayfa</Link>
        <Link to="/pdf-upload">PDF Yükle</Link>
        <Link to="/comparison-results">Sonuçlar</Link>
      </div>
    </nav>
  )
}
