import React, { useEffect, useState } from 'react';
import './EditVariationModal.css';

const EditVariationModal = ({ open, variation, onSave, onCancel }) => {
  const [label, setLabel] = useState('');
  const [content, setContent] = useState('');

  useEffect(() => {
    if (variation) {
      setLabel(variation.label || '');
      // support different possible content keys
      setContent(variation.value ?? variation.content ?? variation.prompt ?? '');
    }
  }, [variation]);

  if (!open) return null;

  const handleSave = (e) => {
    e.preventDefault();
    if (onSave) {
      // send updated content under `value` key (common shape) so parent can persist
      onSave({ value: content });
    }
  };

  return (
    <div className="ev-modal-overlay" role="dialog" aria-modal="true">
      <div className="ev-modal">
        <header className="ev-modal__header">
          <h3 className="ev-modal__title">Edit Variation</h3>
        </header>
        <form className="ev-modal__body" onSubmit={handleSave}>
          <div className="ev-field">
            <span className="ev-field__label">Label</span>
            <div className="ev-field__readonly">{label}</div>
          </div>

          <label className="ev-field">
            <span className="ev-field__label">Content</span>
            <textarea
              className="ev-textarea"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Edit the variation content"
              rows={6}
              autoFocus
            />
          </label>

          <div className="ev-modal__actions">
            <button type="button" className="ev-btn ev-btn--muted" onClick={onCancel}>Cancel</button>
            <button type="submit" className="ev-btn ev-btn--primary">Save</button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default EditVariationModal;
