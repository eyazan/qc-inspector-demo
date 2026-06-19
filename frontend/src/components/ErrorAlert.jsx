import React from 'react'

export default function ErrorAlert({ message, onClose }) {
  return (
    <div className="error">
      {message}
      {onClose && (
        <button onClick={onClose} style={{ marginLeft: '10px', background: 'none', border: 'none', cursor: 'pointer' }}>
          X
        </button>
      )}
    </div>
  )
}