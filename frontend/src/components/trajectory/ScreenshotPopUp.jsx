import React from 'react';
import PropTypes from 'prop-types';
import './ScreenshotPopUp.css';

// 从legendEntries获取对应sequenceIndex的颜色
const getColorFromLegend = (legendEntries, sequenceIndex) => {
	if (!Array.isArray(legendEntries) || !Number.isFinite(sequenceIndex)) {
		return '#6B7280'; // 默认灰色
	}
	
	const entry = legendEntries.find(e => e.sequenceIndex === sequenceIndex);
	return entry?.color || '#6B7280';
};

const ScreenshotPopUp = ({ node, legendEntries, onClose }) => {
	if (!node) return null;

	return (
		<div className="trajectory-modal" onClick={onClose}>
			<div className="trajectory-modal__content" onClick={(e) => e.stopPropagation()}>
				<button
					type="button"
					className="trajectory-modal__close"
					onClick={onClose}
					aria-label="Close image"
				>
					<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
						<line x1="18" y1="6" x2="6" y2="18"></line>
						<line x1="6" y1="6" x2="18" y2="18"></line>
					</svg>
				</button>
				<img src={node.src} alt="Step detail" className="trajectory-modal__image" />
				<div className="trajectory-modal__details">
					{node.occurrences && node.occurrences.map((occ, index) => {
						const output = occ.model_output || occ.raw?.model_output || occ.raw || {};
						const modelOutput = {
							memory: output?.memory || null,
						};

						// 获取legend颜色（根据sequenceIndex）
						const sequenceIndex = Number.isFinite(occ.sequenceIndex) ? occ.sequenceIndex : null;
						const agentColor = getColorFromLegend(legendEntries, sequenceIndex);

						// Detect duplicates for this agent (sequenceIndex)
						const occurrenceCount = node.occurrences.filter((o) => o.sequenceIndex === sequenceIndex).length;
						const isDuplicate = occurrenceCount > 1;

						// 构建 agent 信息
						const agentModel = occ.agentModel || null;
						const agentLabel = agentModel || 'Unknown Agent';

						// 如果没有 memory，但有其他数据，仍然显示
						const hasContent = modelOutput.memory || occ.description || occ.sequenceLabel;

						if (!hasContent) return null;

						return (
							<div key={index} className="trajectory-modal__memory-item" style={{ borderLeftColor: agentColor }}>
								<div className="trajectory-modal__memory-header" style={{ borderBottomColor: agentColor }}>
									<span className="trajectory-modal__memory-color-dot" style={{ backgroundColor: agentColor }}></span>
									<strong>Agent:</strong> {agentLabel}
									{occ.agentValue && occ.agentValue !== agentLabel && (
										<span className="trajectory-modal__memory-value"> ({occ.agentValue})</span>
									)}
									{occ.agentRunIndex !== undefined && occ.agentRunIndex !== null && (
										<span className="trajectory-modal__memory-runindex"> (Run #{occ.agentRunIndex})</span>
									)}
									<span style={{ marginLeft: '8px', fontWeight: 'bold' }}>
										Step {occ.position}
									</span>
									{isDuplicate && (
										<span
											style={{
												marginLeft: '8px',
												backgroundColor: '#fee2e2',
												color: '#b91c1c',
												padding: '2px 6px',
												borderRadius: '4px',
												fontSize: '0.8em',
												fontWeight: 'bold',
											}}
											title="This agent visited this state multiple times"
										>
											Duplicate
										</span>
									)}
								</div>
								{occ.description && (
									<div className="trajectory-modal__memory-sub">
										<strong>Action:</strong> {occ.description}
									</div>
								)}
								{modelOutput.memory && (
									<div className="trajectory-modal__memory-content">
										{modelOutput.memory}
									</div>
								)}
							</div>
						);
					})}
				</div>
			</div>
		</div>
	);
};

ScreenshotPopUp.propTypes = {
	node: PropTypes.shape({
		src: PropTypes.string,
		occurrences: PropTypes.arrayOf(PropTypes.object),
	}),
	legendEntries: PropTypes.arrayOf(
		PropTypes.shape({
			sequenceIndex: PropTypes.number,
			color: PropTypes.string,
		}),
	),
	onClose: PropTypes.func.isRequired,
};

ScreenshotPopUp.defaultProps = {
	legendEntries: [],
};

export default ScreenshotPopUp;
