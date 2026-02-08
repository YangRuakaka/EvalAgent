import React, { useState, useEffect } from 'react';

import './ConfigurationCommon.css';
import './PersonaConfiguration.css';


/*
  This component now contains both the persona form inputs and the value-variation
  selectors + variation list. It is intentionally driven by props from
  ConfigurationPanel to keep state centralized there.

  Expected additional props (besides formData/errors/onInputChange):
   - personaGallery, selectedPersonaId, handlePersonaSelect
   - selectedVariationValues, isValueDropdownOpen, toggleValueDropdown
   - handleValueToggle, valueOptions
   - dropdownRef
   - variationError
   - personaVariations, editingVariationId, variationEditValue
   - handleStartVariationEdit, handleVariationEditChange, handleSaveVariationEdit, handleCancelVariationEdit
   - handleVariationRegeneration, isGeneratingVariation, regeneratingVariationKey
   - formatVariationContent
*/

const PersonaConfiguration = ({
  formData,
  errors,
  onInputChange,
  personaGallery = [],
  selectedPersonaId,
  handlePersonaSelect,
  selectedVariationValues = [],
  isValueDropdownOpen = false,
  toggleValueDropdown,
  handleValueToggle,
  valueOptions = [],
  dropdownRef,
  variationError,
  personaVariations = [],
  editingVariationId,
  variationEditValue,
  handleStartVariationEdit,
  handleVariationEditChange,
  handleSaveVariationEdit,
  handleCancelVariationEdit,
  handleVariationRegeneration,
  isGeneratingVariation,
  regeneratingVariationKey,
  formatVariationContent,
  selectedPersona,
  // persona result + editing handlers (moved from ConfigurationPanel)
  personaResult,
  isEditing,
  editValue,
  handleConfirmPersona,
  handleEditPersona,
  handleEditChange,
  handleSaveEdit,
  handleCancelEdit,
  handleDiscardPersona,
  showSavedToast,
}) => {
  // Keep a local "sticky" copy of the most recently generated persona so
  // the generated persona box remains visible even if the parent clears
  // `personaResult` after saving or other actions.
  const [stickyPersonaResult, setStickyPersonaResult] = useState(null);

  useEffect(() => {
    if (personaResult) {
      setStickyPersonaResult(personaResult);
    }
  }, [personaResult]);

  const hasLiveResult = Boolean(personaResult);
  const displayedPersona = personaResult || stickyPersonaResult;
  return (
    <div className="config-form__container">
      {/* Persona Input Section */}
      <section className="config-form__section">
        <div className="config-form__grid">
          <div className="config-form__field config-form__field--name">
            <label className="config-form__label" htmlFor="persona-name">
              Full Name
            </label>
            <input
              id="persona-name"
              name="name"
              type="text"
              className="config-form__input"
              placeholder="Enter full name"
              value={formData.name}
              onChange={onInputChange}
            />
            {errors.name && <p className="config-form__error">{errors.name}</p>}
          </div>
          <div className="config-form__field config-form__field--age">
            <label className="config-form__label" htmlFor="persona-age">
              Age
            </label>
            <input
              id="persona-age"
              name="age"
              type="number"
              min="18"
              max="100"
              step="1"
              className="config-form__input"
              placeholder="Enter age"
              value={formData.age}
              onChange={onInputChange}
            />
            {errors.age && <p className="config-form__error">{errors.age}</p>}
          </div>
          <div className="config-form__field config-form__field--job">
            <label className="config-form__label" htmlFor="persona-job">
              Profession
            </label>
            <input
              id="persona-job"
              name="job"
              type="text"
              className="config-form__input"
              placeholder="Enter profession"
              value={formData.job}
              onChange={onInputChange}
            />
            {errors.job && <p className="config-form__error">{errors.job}</p>}
          </div>
          <div className="config-form__field config-form__field--location">
            <label className="config-form__label" htmlFor="persona-location">
              Location
            </label>
            <input
              id="persona-location"
              name="location"
              type="text"
              className="config-form__input"
              placeholder="Enter location (optional)"
              value={formData.location}
              onChange={onInputChange}
            />
            {errors.location && <p className="config-form__error">{errors.location}</p>}
          </div>
          <div className="config-form__field config-form__field--education">
            <label className="config-form__label" htmlFor="persona-education">
              Education
            </label>
            <input
              id="persona-education"
              name="education"
              type="text"
              className="config-form__input"
              placeholder="Enter education background (optional)"
              value={formData.education}
              onChange={onInputChange}
            />
            {errors.education && <p className="config-form__error">{errors.education}</p>}
          </div>
          <div className="config-form__field config-form__field--job">
            <label className="config-form__label" htmlFor="persona-interests">
              Interests
            </label>
            <input
              id="persona-interests"
              name="interests"
              type="text"
              className="config-form__input"
              placeholder="Enter interests (optional)"
              value={formData.interests}
              onChange={onInputChange}
            />
            {errors.interests && <p className="config-form__error">{errors.interests}</p>}
          </div>
        </div>
      </section>

      {/* Generated Persona Result */}
      {displayedPersona && (
        <section className="config-persona-result">
          <div className="config-persona-result__header">
            <h4 className="config-persona-result__title">Generated Persona</h4>
            <div className="config-persona-result__actions">
              <button
                type="button"
                className="panel__action config-persona-result__button"
                onClick={handleConfirmPersona}
                disabled={!hasLiveResult || personaResult?.saved || isEditing}
              >
                Confirm
              </button>
              <button
                type="button"
                className="panel__action config-persona-result__button"
                onClick={handleEditPersona}
                disabled={!hasLiveResult || isEditing}
              >
                Edit
              </button>
              <button
                type="button"
                className="panel__action config-persona-result__button"
                onClick={() => {
                  if (hasLiveResult) {
                    handleDiscardPersona?.();
                  } else {
                    setStickyPersonaResult(null);
                  }
                }}
              >
                Discard
              </button>
            </div>
          </div>
          {isEditing && hasLiveResult ? (
            <textarea
              className="config-persona-result__editor"
              value={editValue}
              onChange={handleEditChange}
              rows={8}
            />
          ) : (
            <pre className="config-persona-result__content">{displayedPersona.content}</pre>
          )}
          {isEditing && hasLiveResult && (
            <div className="config-persona-result__footer">
              <button
                type="button"
                className="panel__action config-persona-result__button"
                onClick={handleSaveEdit}
              >
                Save
              </button>
              <button
                type="button"
                className="panel__action config-persona-result__button"
                onClick={handleCancelEdit}
              >
                Cancel
              </button>
            </div>
          )}
        </section>
      )}

      {showSavedToast && (
        <div className="save-toast" role="status">Save Success</div>
      )}

      {/* Value-Variation Selection Section */}
      <section className="config-form__section">
        <div className="config-value-variation__selectors" ref={dropdownRef}>
          <div className="config-value-variation__gallery">
            <label className="config-value-variation__label" htmlFor="value-variation-persona">
              Persona Gallery
            </label>
            <div className="config-value-variation__select-wrapper">
              <select
                id="value-variation-persona"
                className="config-value-variation__select"
                value={selectedPersonaId}
                onChange={handlePersonaSelect}
                disabled={personaGallery.length === 0}
              >
                <option value="">Select a persona</option>
                {personaGallery.map((persona) => (
                  <option key={persona.id} value={persona.id}>
                    {persona.name}
                  </option>
                ))}
              </select>
              <span className="config-value-variation__dropdown-indicator" aria-hidden="true">▾</span>
            </div>
          </div>
          <div className="config-value-variation__controls">
            <span className="config-value-variation__label">Select Values</span>
            <div className={`config-value-variation__dropdown${isValueDropdownOpen ? ' config-value-variation__dropdown--open' : ''}`}>
              <button
                type="button"
                className="config-value-variation__dropdown-trigger"
                onClick={toggleValueDropdown}
                disabled={!selectedPersonaId}
                aria-haspopup="listbox"
                aria-expanded={isValueDropdownOpen}
              >
                {selectedVariationValues.length > 0 ? 'Adjust Values' : 'Select Values'}
                <span className="config-value-variation__dropdown-indicator" aria-hidden="true">▾</span>
              </button>
              {isValueDropdownOpen && (
                <div className="config-value-variation__dropdown-menu" role="listbox">
                  {valueOptions.map((option) => {
                    const isChecked = selectedVariationValues.includes(option.value);
                    return (
                      <label key={option.value} className="config-value-variation__option">
                        <input
                          type="checkbox"
                          className="config-value-variation__option-input"
                          checked={isChecked}
                          onChange={() => handleValueToggle(option.value)}
                        />
                        <span className="config-value-variation__option-color" style={{ backgroundColor: option.color }} />
                        <span className="config-value-variation__option-label">{option.label}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="config-value-variation__chips">
              {selectedVariationValues.map((value) => {
                const option = valueOptions.find((item) => item.value === value);
                if (!option) {
                  return null;
                }
                return (
                  <span key={value} className="config-value-variation__chip" style={{ backgroundColor: option.color, color: option.textColor }}>
                    {option.label}
                  </span>
                );
              })}
            </div>
          </div>
        </div>

        {/* Unified Hint: Show only when persona or values are not selected */}
        {(!selectedPersonaId || selectedVariationValues.length === 0) && (
          <div className="config-value-variation__hints-row">
            <p className="config-value-variation__hint">Select a persona and at least one value to generate variations.</p>
          </div>
        )}

        {variationError && <p className="config-form__error config-form__error--global">{variationError}</p>}

        {/* Variation list (if any) */}
        {selectedPersonaId && personaVariations.length > 0 && (
          <div className="config-value-variation__list">
            {personaVariations.map((variation) => {
              const option = valueOptions.find((item) => item.value === variation.valueKey);
              const accentColor = variation.color || option?.color || '#e5e7eb';
              const highlightColor = variation.textColor || option?.textColor || '#1f2937';
              const variationLabel = variation.label || option?.label || variation.valueKey;
              const isVariationEditing = editingVariationId === variation.valueKey;
              const isSelected = selectedVariationValues.includes(variation.valueKey);
              const isRegenerating = regeneratingVariationKey === variation.valueKey;
              const formattedContent = formatVariationContent(variation.content, highlightColor);
              const hasContent = Boolean(variation.content);

              if (!isSelected) return null;

              return (
                <article key={variation.valueKey} className="config-value-variation__item">
                  <div className="config-value-variation__item-header">
                    <h5 className="config-value-variation__item-title">
                      <span className="config-value-variation__color-dot" style={{ backgroundColor: accentColor }} />
                      {variationLabel} Persona Variation
                    </h5>
                    <div className="config-value-variation__item-actions">
                      {isVariationEditing ? (
                        <>
                          <button type="button" className="panel__action config-value-variation__button" onClick={handleSaveVariationEdit}>Save</button>
                          <button type="button" className="panel__action config-value-variation__button" onClick={handleCancelVariationEdit}>Cancel</button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="panel__action config-value-variation__button"
                            onClick={() => handleVariationRegeneration(variation.valueKey)}
                            disabled={isRegenerating || isGeneratingVariation}
                          >
                            {isRegenerating
                              ? (hasContent ? 'Regenerating...' : 'Generating...')
                              : (hasContent ? 'Regenerate' : 'Generate')}
                          </button>
                          <button type="button" className="panel__action config-value-variation__button" onClick={() => handleStartVariationEdit(variation.valueKey)}>Edit</button>
                        </>
                      )}
                    </div>
                  </div>
                  {isVariationEditing ? (
                    <textarea className="config-value-variation__editor" rows={6} value={variationEditValue} onChange={handleVariationEditChange} />
                  ) : (
                    <pre className="config-value-variation__item-content" dangerouslySetInnerHTML={{ __html: formattedContent }} />
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};

export default PersonaConfiguration;
