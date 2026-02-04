
export const createCriteriaDragData = (criterion) => {
  return JSON.stringify({
    type: 'criteria',
    criterionId: criterion.id,
    criterionName: criterion.name,
    description: criterion.description,
  });
};

export const parseCriteriaDragData = (dataTransfer) => {
  try {
    const data = JSON.parse(dataTransfer.getData('application/json'));
    if (data.type === 'criteria') {
      return data;
    }
  } catch (e) {
    console.error('Failed to parse drag data:', e);
  }
  return null;
};

export const verdictToColor = {
  'PASS': { bg: '#d1fae5', text: '#065f46', border: '#10b981', icon: '✓' },
  'FAIL': { bg: '#fee2e2', text: '#7f1d1d', border: '#ef4444', icon: '✕' },
  'PARTIAL': { bg: '#fef3c7', text: '#78350f', border: '#f59e0b', icon: '◐' },
  'UNABLE_TO_EVALUATE': { bg: '#f3f4f6', text: '#374151', border: '#9ca3af', icon: '?' },
};


export const evaluateStatusMap = {
  'pass': { bg: '#d1fae5', text: '#065f46', border: '#10b981', label: 'Pass', icon: '✓' },
  'fail': { bg: '#fee2e2', text: '#7f1d1d', border: '#ef4444', label: 'Fail', icon: '✕' },
  'partial': { bg: '#fef3c7', text: '#78350f', border: '#f59e0b', label: 'Partial', icon: '◐' },
  'unevaluated': { bg: '#f3f4f6', text: '#374151', border: '#9ca3af', label: 'Not Evaluated', icon: '○' },
};

export const granularityLabels = {
  'STEP_LEVEL': '单步评估',
  'SUBTASK_CLUSTER': '任务块评估',
  'GLOBAL_SUMMARY': '全局评估',
};

export const evaluationAffectsStep = (evaluation, stepIndex) => {
  return evaluation.relevant_steps.includes(stepIndex);
};

export const evaluationAffectsRange = (evaluation, startIdx, endIdx) => {
  return evaluation.relevant_steps.some(idx => idx >= startIdx && idx <= endIdx);
};

/**
 * 结合criteria颜色和verdict状态
 * 背景用criteria颜色，边框和icon用verdict颜色
 * @param {string} criteriaId - criteria的唯一标识
 * @param {string} verdict - 评估结果 (PASS, FAIL, PARTIAL, UNABLE_TO_EVALUATE)
 * @param {Object} criteriaBaseColor - criteria的基础颜色 {backgroundColor, borderColor, color}
 * @returns {Object} 结合后的颜色信息 {criteriaBackground, verdictBorder, verdictText, verdictIcon}
 */
export const getCriteriaVerdictColors = (criteriaId, verdict = 'UNABLE_TO_EVALUATE', criteriaBaseColor = null) => {
  const verdictConfig = verdictToColor[verdict] || verdictToColor['UNABLE_TO_EVALUATE'];
  
  // 如果没有提供criteria颜色，直接返回verdict颜色
  if (!criteriaBaseColor) {
    return {
      bg: verdictConfig.bg,
      text: verdictConfig.text,
      border: verdictConfig.border,
      icon: verdictConfig.icon,
    };
  }
  
  // 背景用criteria颜色，边框和icon用verdict颜色
  return {
    criteriaBackground: criteriaBaseColor.backgroundColor,
    criteriaText: criteriaBaseColor.color,
    verdictBorder: verdictConfig.border,
    verdictText: verdictConfig.text,
    verdictIcon: verdictConfig.icon,
  };
};
