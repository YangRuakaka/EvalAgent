import React, { useState } from 'react';
import './ConfigurationCommon.css';
import './EnvironmentSetting.css';
import EditVariationModal from '../common/EditVariationModal';


const EnvironmentSetting = ({
  personaGallery,
  environmentPersonaId,
  handleEnvironmentPersonaChange,
  environmentErrors,
  environmentPersona,
  environmentPersonaVariations,
  environmentVariationIds,
  handleEnvironmentVariationToggle,
  // optional callback: (variationId, updates) => void
  handleEnvironmentVariationUpdate,
  VALUE_VARIATION_OPTIONS,
  formatVariationContent,
  environmentTaskName,
  environmentTaskUrl,
  onEnvironmentTaskNameChange,
  onEnvironmentTaskUrlChange,
  environmentRunTimes,
  handleEnvironmentRunTimesChange,
  ENVIRONMENT_MODEL_OPTIONS,
  environmentModels,
  handleEnvironmentModelToggle,
  environmentRunError,
  environmentRunResult,
}) => {
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editVariation, setEditVariation] = useState(null);

  const openEditVariation = (variation) => {
    setEditVariation(variation);
    setIsEditOpen(true);
  };

  const handleEditCancel = () => {
    setIsEditOpen(false);
    setEditVariation(null);
  };

  const handleEditSave = (updates) => {
    if (!editVariation) return;
    if (typeof handleEnvironmentVariationUpdate === 'function') {
      handleEnvironmentVariationUpdate(editVariation.valueKey, updates);
    } else {
      // if no handler provided, just warn — parent must persist
      // We intentionally do not mutate props here.
      // Consumer can pass handleEnvironmentVariationUpdate to persist edits.
      // eslint-disable-next-line no-console
      console.warn('handleEnvironmentVariationUpdate not provided; edit will not persist to parent');
    }
    setIsEditOpen(false);
    setEditVariation(null);
  };



  const handleTaskNameChange = (value) => {
    onEnvironmentTaskNameChange(value);
  };

  const handleTaskUrlChange = (value) => {
    onEnvironmentTaskUrlChange(value);
  };
  return (
    <section className="config-form__container">
      <div className="config-environment__grid">
        {/* Row: Persona/Variations (left) and Models (right) */}
        <div className="config-selection-row">
          <div className="config-panel">
            <label className="config-panel__title" htmlFor="environment-persona">Persona</label>
            <select
              id="environment-persona"
              className="config-environment__select"
              value={environmentPersonaId}
              onChange={handleEnvironmentPersonaChange}
              disabled={personaGallery.length === 0}
            >
              <option value="">Select a persona</option>
              {personaGallery.map((persona) => (
                <option key={persona.id} value={persona.id}>
                  {persona.name}
                </option>
              ))}
            </select>
            {personaGallery.length === 0 && (
              <p className="config-environment__hint">No personas saved yet.</p>
            )}
            {environmentErrors.persona && (
              <p className="config-form__error">{environmentErrors.persona}</p>
            )}

            <div className="config-panel__body">
              <span className="config-environment__label">Variations</span>
              {environmentPersona && (
                <p className="config-environment__hint">
                  Active persona: <span className="config-environment__hint-accent">{environmentPersona.name}</span>
                </p>
              )}

              {environmentPersonaId ? (
                environmentPersonaVariations.filter(v => v.content).length > 0 ? (
                  <div className="config-panel__card-list">
                    {environmentPersonaVariations
                      .filter((v) => !environmentVariationIds.includes(v.valueKey))
                      .filter((v) => v.content)
                      .map((variation) => {
                        const option = VALUE_VARIATION_OPTIONS.find((item) => item.value === variation.valueKey);
                        const accentColor = variation.color || option?.color || '#e5e7eb';
                        const label = `${environmentPersona?.name || 'Persona'} • ${variation.label || option?.label || variation.valueKey}`;
                        return (
                          <div key={variation.valueKey} className="config-card">
                            <div className="config-card__left">
                              <span className="config-card__dot" style={{ backgroundColor: accentColor }} />
                              <span className="config-card__label">{label}</span>
                            </div>
                            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                              <button
                                type="button"
                                className="config-card__edit"
                                onClick={() => openEditVariation(variation)}
                                aria-label={`Edit ${label}`}
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                className="config-card__add"
                                onClick={() => handleEnvironmentVariationToggle(variation.valueKey)}
                                aria-label={`Add ${label}`}
                              >
                                +
                              </button>
                            </div>
                          </div>
                        );
                      })}
                  </div>
                ) : (
                  <p className="config-environment__hint">No variations generated for this persona yet.</p>
                )
              ) : (
                <p className="config-environment__hint">Select a persona to choose variations.</p>
              )}

              {environmentErrors.variations && (
                <p className="config-form__error">{environmentErrors.variations}</p>
              )}
            </div>
          </div>

          <div className="config-panel">
            <span className="config-panel__title">Models</span>
            <div className="config-panel__body">
              <div className="config-panel__card-list">
                {ENVIRONMENT_MODEL_OPTIONS.filter((opt) => !environmentModels.includes(opt.value)).map((option) => (
                  <div key={option.value} className="config-card">
                    <div className="config-card__left">
                      <span className="config-card__label">{option.label}</span>
                    </div>
                    <button
                      type="button"
                      className="config-card__add"
                      onClick={() => handleEnvironmentModelToggle(option.value)}
                      aria-label={`Add model ${option.label}`}
                    >
                      +
                    </button>
                  </div>
                ))}
              </div>
              {environmentErrors.model && (
                <p className="config-form__error">{environmentErrors.model}</p>
              )}
            </div>
          </div>
        </div>

        {/* Task configuration (full width below the two selection panels) */}
        <div className="config-panel config-panel--full">
          {/* Selected items (persona + models) - separated into distinct sections */}
          <div className="selected-items-container">
            {/* Selected Persona Variations Section */}
            {environmentVariationIds && environmentVariationIds.length > 0 && (
              <div className="selected-items-section">
                <span className="selected-items-section__label">Selected Personas</span>
                <div className="selected-cards">
                  {environmentVariationIds.map((variationId) => {
                    // find variation metadata from current persona variations or fallback to VALUE_VARIATION_OPTIONS
                    const variation = environmentPersonaVariations.find((v) => v.valueKey === variationId) || {};
                    const option = VALUE_VARIATION_OPTIONS.find((o) => o.value === variationId) || {};
                    const accentColor = variation.color || option.color || '#e5e7eb';
                    const label = `${environmentPersona?.name || 'Persona'} • ${variation.label || option.label || variationId}`;
                    return (
                      <div className="selected-card" key={variationId}>
                        <div className="selected-card__left">
                          <span className="config-card__dot" style={{ backgroundColor: accentColor, width: 12, height: 12 }} />
                          <span className="selected-card__label">{label}</span>
                        </div>
                        <button
                          type="button"
                          className="selected-card__remove"
                          onClick={() => handleEnvironmentVariationToggle(variationId)}
                          aria-label={`Remove variation ${label}`}
                        >
                          −
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Selected Models Section */}
            {environmentModels && environmentModels.length > 0 && (
              <div className="selected-items-section">
                <span className="selected-items-section__label">Selected Models</span>
                <div className="selected-cards">
                  {environmentModels.map((modelValue) => {
                    const opt = ENVIRONMENT_MODEL_OPTIONS.find((o) => o.value === modelValue);
                    const label = opt?.label || modelValue;
                    return (
                      <div className="selected-card" key={modelValue}>
                        <div className="selected-card__left">
                          <span className="selected-card__label">{label}</span>
                        </div>
                        <button
                          type="button"
                          className="selected-card__remove"
                          onClick={() => handleEnvironmentModelToggle(modelValue)}
                          aria-label={`Remove model ${label}`}
                        >
                          −
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          <div className="config-panel__body">
            <span className="config-panel__title">Task</span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, alignItems: 'flex-start' }}>
              <div className="config-environment__field">
                <label className="config-environment__label" htmlFor="task-name">Task Name</label>
                <input
                  id="task-name"
                  type="text"
                  className="config-environment__select"
                  value={environmentTaskName}
                  onChange={(e) => handleTaskNameChange(e.target.value)}
                  placeholder="e.g., Buy a product"
                />
              </div>

              <div className="config-environment__field">
                <label className="config-environment__label" htmlFor="task-url">Target URL</label>
                <select
                  id="task-url"
                  className="config-environment__select"
                  value={environmentTaskUrl}
                  onChange={(e) => handleTaskUrlChange(e.target.value)}
                >
                  <option value="">Select a target</option>
                  <option value="http://localhost:3000/riverbuy">RiverBuy</option>
                  <option value="http://localhost:3000/zoomcar">ZoomCar</option>
                  <option value="http://localhost:3000/dwellio">Dwellio</option>
                </select>
              </div>
            </div>
            {environmentErrors.tasks && (
              <p className="config-form__error">{environmentErrors.tasks}</p>
            )}
          </div>

          <div className="config-environment__field config-environment__field--inline compact-controls" style={{ marginTop: 12 }}>
            <div className="config-environment__control">
              <label className="config-environment__label" htmlFor="environment-run-times">Run Times</label>
              <input
                id="environment-run-times"
                type="number"
                min="1"
                max="10"
                step="1"
                className="config-environment__select config-environment__select--input"
                value={environmentRunTimes}
                onChange={handleEnvironmentRunTimesChange}
              />
              {environmentErrors.run_times && (
                <p className="config-form__error">{environmentErrors.run_times}</p>
              )}
            </div>
          </div>

          {environmentRunError && (
            <p className="config-form__error config-form__error--global">{environmentRunError}</p>
          )}
          {environmentRunResult && (
            <div className="config-environment__result">
              <h5 className="config-environment__result-title">Last Run Response</h5>
              <pre className="config-environment__result-content">{JSON.stringify(environmentRunResult, null, 2)}</pre>
            </div>
          )}
        </div>
      </div>
      {/* Edit variation modal (common component) */}
      <EditVariationModal
        open={isEditOpen}
        variation={editVariation}
        onSave={handleEditSave}
        onCancel={handleEditCancel}
      />
    </section>
  );
};

export default EnvironmentSetting;
