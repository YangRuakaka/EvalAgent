import React, { useState } from 'react';
import PropTypes from 'prop-types';

import PanelHeader from '../common/PanelHeader';
import EnvironmentSetting from '../configuration/EnvironmentSetting';
import PersonaConfiguration from '../configuration/PersonaConfiguration';

import { usePersonaConfiguration } from '../../hooks/usePersonaConfiguration';
import { useEnvironmentConfiguration } from '../../hooks/useEnvironmentConfiguration';
import { ENVIRONMENT_MODEL_OPTIONS, VALUE_VARIATION_OPTIONS } from '../../config/constants';

import './ConfigurationView.css';

const ConfigurationView = ({
	onAddRun,
	activeTab: externalActiveTab,
	onTabChange: externalOnTabChange,
	onGetCacheData,
	isCacheLoading,
	onEnvironmentRunStateChange,
}) => {
	const [activeTab, setActiveTab] = useState('persona'); // 'persona' | 'environment'
	
	// Use external tab state if provided, otherwise use internal state
	const currentActiveTab = externalActiveTab !== undefined ? externalActiveTab : activeTab;
	const switchConfigTab = (nextTab) => {
		if (typeof externalOnTabChange === 'function') {
			externalOnTabChange(nextTab);
			return;
		}
		setActiveTab(nextTab);
	};

    const personaConfig = usePersonaConfiguration();
    const environmentConfig = useEnvironmentConfiguration(
        personaConfig.variationStateByPersona,
        personaConfig.setVariationStateByPersona,
        personaConfig.personaGallery,
        onAddRun,
        onEnvironmentRunStateChange,
        isCacheLoading
    );

	const handleContinueToEnvironment = () => {
		switchConfigTab('environment');
	};

	return (
		<div className="configuration-panel">
			<PanelHeader title="Configuration" />
			<div className="config-container">
				{/* Content area */}
				<div className="panel__body config-content">
					<section className="config-section">
							{currentActiveTab === 'persona' && (
								<form id="persona-form" className="config-form" onSubmit={personaConfig.handlePersonaGeneration} noValidate>
									<PersonaConfiguration
										formData={personaConfig.formData}
										personaModel={personaConfig.personaModel}
										onModelChange={personaConfig.setPersonaModel}
										modelOptions={ENVIRONMENT_MODEL_OPTIONS}
										errors={personaConfig.errors}
										onInputChange={personaConfig.handleInputChange}
										personaGallery={personaConfig.personaGallery}
										selectedPersonaId={personaConfig.selectedPersonaId}
										handlePersonaSelect={personaConfig.handlePersonaSelect}
										selectedVariationValues={personaConfig.selectedVariationValues}
										isValueDropdownOpen={personaConfig.isValueDropdownOpen}
										toggleValueDropdown={personaConfig.toggleValueDropdown}
										handleValueToggle={personaConfig.handleValueToggle}
										valueOptions={VALUE_VARIATION_OPTIONS}
										dropdownRef={personaConfig.dropdownRef}
										variationError={personaConfig.variationError}
										personaVariations={personaConfig.personaVariations}
										editingVariationId={personaConfig.editingVariationId}
										variationEditValue={personaConfig.variationEditValue}
										handleStartVariationEdit={personaConfig.handleStartVariationEdit}
										handleVariationEditChange={personaConfig.handleVariationEditChange}
										handleSaveVariationEdit={personaConfig.handleSaveVariationEdit}
										handleCancelVariationEdit={personaConfig.handleCancelVariationEdit}
										handleVariationGeneration={personaConfig.handleVariationGeneration}
										handleVariationRegeneration={personaConfig.handleVariationRegeneration}
										isGenerating={personaConfig.isGenerating}
										isGeneratingVariation={personaConfig.isGeneratingVariation}
										regeneratingVariationKey={personaConfig.regeneratingVariationKey}
										formatVariationContent={personaConfig.formatVariationContent}
										selectedPersona={personaConfig.selectedPersona}
										personaResult={personaConfig.personaResult}
										isEditing={personaConfig.isEditing}
										editValue={personaConfig.editValue}
										handleConfirmPersona={personaConfig.handleConfirmPersona}
										handleEditPersona={personaConfig.handleEditPersona}
										handleEditChange={personaConfig.handleEditChange}
										handleSaveEdit={personaConfig.handleSaveEdit}
										handleCancelEdit={personaConfig.handleCancelEdit}
										handleDiscardPersona={() => personaConfig.handleDiscardPersona(
                                            environmentConfig.environmentPersonaId,
                                            environmentConfig.setEnvironmentPersonaId,
                                            environmentConfig.setEnvironmentVariationIds
                                        )}
										showSavedToast={personaConfig.showSavedToast}
										hasCompletedVariationGeneration={personaConfig.hasCompletedVariationGeneration}
										onContinueToEnvironment={handleContinueToEnvironment}
									/>
									{personaConfig.errors.submit && <p className="config-form__error config-form__error--global">{personaConfig.errors.submit}</p>}
								</form>
							)}

							{currentActiveTab === 'environment' && (
								<EnvironmentSetting
									personaGallery={personaConfig.personaGallery}
									environmentPersonaId={environmentConfig.environmentPersonaId}
									handleEnvironmentPersonaChange={environmentConfig.handleEnvironmentPersonaChange}
									environmentErrors={environmentConfig.environmentErrors}
									environmentPersona={environmentConfig.environmentPersona}
									environmentPersonaVariations={environmentConfig.environmentPersonaVariations}
									environmentVariationIds={environmentConfig.environmentVariationIds}
									handleEnvironmentVariationToggle={environmentConfig.handleEnvironmentVariationToggle}
									handleEnvironmentVariationUpdate={environmentConfig.handleEnvironmentVariationUpdate}
									VALUE_VARIATION_OPTIONS={VALUE_VARIATION_OPTIONS}
									formatVariationContent={personaConfig.formatVariationContent}
									environmentTasks={[]}
									environmentTaskName={environmentConfig.environmentTaskName}
									environmentTaskUrl={environmentConfig.environmentTaskUrl}
									onEnvironmentTaskNameChange={environmentConfig.setEnvironmentTaskName}
									onEnvironmentTaskUrlChange={environmentConfig.setEnvironmentTaskUrl}
									environmentRunTimes={environmentConfig.environmentRunTimes}
									handleEnvironmentRunTimesChange={environmentConfig.handleEnvironmentRunTimesChange}
									ENVIRONMENT_MODEL_OPTIONS={ENVIRONMENT_MODEL_OPTIONS}
									environmentModels={environmentConfig.environmentModels}
									handleEnvironmentModelToggle={environmentConfig.handleEnvironmentModelToggle}
									environmentRunError={environmentConfig.environmentRunError}
									environmentRunResult={environmentConfig.environmentRunResult}
									handleEnvironmentRun={environmentConfig.handleEnvironmentRun}
									isRunningEnvironment={environmentConfig.isRunningEnvironment}
									environmentWaitSeconds={environmentConfig.environmentWaitSeconds}
									isCacheLoading={isCacheLoading}
								/>
							)}
						</section>
					</div>
				</div>
			</div>
		);
	};

ConfigurationView.propTypes = {
	onAddRun: PropTypes.func,
	activeTab: PropTypes.oneOf(['persona', 'environment']),
	onTabChange: PropTypes.func,
	onGetCacheData: PropTypes.func,
	isCacheLoading: PropTypes.bool,
	onEnvironmentRunStateChange: PropTypes.func,
};

ConfigurationView.defaultProps = {
	onAddRun: undefined,
	activeTab: undefined,
	onTabChange: undefined,
	onGetCacheData: undefined,
	isCacheLoading: false,
	onEnvironmentRunStateChange: undefined,
};

export default ConfigurationView;