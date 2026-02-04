import { useState, useCallback, useMemo, useEffect } from 'react';

export function useExperimentsManager(initialExperiments = {}, enableMultiTab = false) {
  const [singleTabExperiments, setSingleTabExperiments] = useState(initialExperiments);

  const [experimentsByTab, setExperimentsByTab] = useState([
    {
      tabId: 'tab-default',
      tabName: 'Default',
      experiments: initialExperiments || {},
    },
  ]);

  const [activeTabId, setActiveTabId] = useState('tab-default');
  useEffect(() => {
    setSingleTabExperiments(initialExperiments);
    
    setExperimentsByTab((prev) => {
      // 检查是否已经有 tab-default
      const defaultTabExists = prev.some(t => t.tabId === 'tab-default');
      
      if (defaultTabExists) {
        return prev.map(t => 
          t.tabId === 'tab-default' 
            ? { ...t, experiments: initialExperiments || {} } 
            : t
        );
      }
      
      return [
        {
          tabId: 'tab-default',
          tabName: 'Default',
          experiments: initialExperiments || {},
        },
      ];
    });
  }, [initialExperiments]);


  const addCriteriaToRow = useCallback((rowId, criteria) => {
    setSingleTabExperiments((prev) => {
      const next = { ...prev };
      const currentList = next[rowId] ? [...next[rowId]] : [];
      
      const exists = currentList.some((c) => c.id === criteria.id);
      if (!exists) {
        currentList.push(criteria);
        next[rowId] = currentList;
      }
      return next;
    });
  }, []);


  const removeCriteriaFromRow = useCallback((rowId, criteriaId) => {
    setSingleTabExperiments((prev) => {
      const next = { ...prev };
      if (next[rowId]) {
        const newList = next[rowId].filter((c) => c.id !== criteriaId);
        if (newList.length === 0) {
          delete next[rowId];
        } else {
          next[rowId] = newList;
        }
      }
      return next;
    });
  }, []);

  const addCriteriaToAllRows = useCallback((rowIds, criteria) => {
    setSingleTabExperiments((prev) => {
      const next = { ...prev };
      rowIds.forEach((rowId) => {
        const currentList = next[rowId] ? [...next[rowId]] : [];
        const exists = currentList.some((c) => c.id === criteria.id);
        if (!exists) {
          currentList.push(criteria);
          next[rowId] = currentList;
        }
      });
      return next;
    });
  }, []);

  const setRowCriteria = useCallback((rowId, criteriaList) => {
    setSingleTabExperiments((prev) => {
      const next = { ...prev };
      if (criteriaList && criteriaList.length > 0) {
        next[rowId] = criteriaList;
      } else {
        delete next[rowId];
      }
      return next;
    });
  }, []);

  const clearAllExperiments = useCallback(() => {
    setSingleTabExperiments({});
  }, []);

  const getTabExperiments = useCallback((tabId) => {
    const tab = experimentsByTab.find((t) => t.tabId === tabId);
    return tab?.experiments || {};
  }, [experimentsByTab]);

  const getCurrentTabExperiments = useCallback(() => {
    return getTabExperiments(activeTabId);
  }, [activeTabId, getTabExperiments]);

  const addCriteriaToTabRow = useCallback(
    (tabId, rowId, criteria) => {
      setExperimentsByTab((prev) =>
        prev.map((tab) => {
          if (tab.tabId !== tabId) {
            return tab;
          }

          const experiments = { ...tab.experiments };
          const currentList = experiments[rowId] ? [...experiments[rowId]] : [];
          
          const exists = currentList.some((c) => c.id === criteria.id);
          if (!exists) {
            currentList.push(criteria);
            experiments[rowId] = currentList;
          }

          return { ...tab, experiments };
        })
      );
    },
    []
  );

  const removeCriteriaFromTabRow = useCallback(
    (tabId, rowId, criteriaId) => {
      setExperimentsByTab((prev) =>
        prev.map((tab) => {
          if (tab.tabId !== tabId) {
            return tab;
          }

          const experiments = { ...tab.experiments };
          if (experiments[rowId]) {
            const newList = experiments[rowId].filter((c) => c.id !== criteriaId);
            if (newList.length === 0) {
              delete experiments[rowId];
            } else {
              experiments[rowId] = newList;
            }
          }

          return { ...tab, experiments };
        })
      );
    },
    []
  );

  const addCriteriaToTabAllRows = useCallback(
    (tabId, rowIds, criteria) => {
      setExperimentsByTab((prev) =>
        prev.map((tab) => {
          if (tab.tabId !== tabId) {
            return tab;
          }

          const experiments = { ...tab.experiments };
          rowIds.forEach((rowId) => {
            const currentList = experiments[rowId] ? [...experiments[rowId]] : [];
            const exists = currentList.some((c) => c.id === criteria.id);
            if (!exists) {
              currentList.push(criteria);
              experiments[rowId] = currentList;
            }
          });

          return { ...tab, experiments };
        })
      );
    },
    []
  );

  const setTabRowCriteria = useCallback(
    (tabId, rowId, criteriaList) => {
      setExperimentsByTab((prev) =>
        prev.map((tab) => {
          if (tab.tabId !== tabId) {
            return tab;
          }

          const experiments = { ...tab.experiments };
          if (criteriaList && criteriaList.length > 0) {
            experiments[rowId] = criteriaList;
          } else {
            delete experiments[rowId];
          }

          return { ...tab, experiments };
        })
      );
    },
    []
  );

  const addTab = useCallback((tabName) => {
    const newTabId = `tab-${Date.now()}`;
    setExperimentsByTab((prev) => [
      ...prev,
      {
        tabId: newTabId,
        tabName: tabName || `Tab ${prev.length + 1}`,
        experiments: {},
      },
    ]);
    return newTabId;
  }, []);

  const removeTab = useCallback((tabId) => {
    setExperimentsByTab((prev) => {
      const filtered = prev.filter((t) => t.tabId !== tabId);
      if (activeTabId === tabId && filtered.length > 0) {
        setActiveTabId(filtered[0].tabId);
      }
      return filtered;
    });
  }, [activeTabId]);

  const renameTab = useCallback((tabId, newName) => {
    setExperimentsByTab((prev) =>
      prev.map((tab) =>
        tab.tabId === tabId ? { ...tab, tabName: newName } : tab
      )
    );
  }, []);

  const duplicateTab = useCallback((tabId) => {
    const sourceTab = experimentsByTab.find((t) => t.tabId === tabId);
    if (!sourceTab) {
      return null;
    }

    const newTabId = `tab-${Date.now()}`;
    setExperimentsByTab((prev) => [
      ...prev,
      {
        tabId: newTabId,
        tabName: `${sourceTab.tabName} (copy)`,
        experiments: JSON.parse(JSON.stringify(sourceTab.experiments)),
      },
    ]);
    return newTabId;
  }, [experimentsByTab]);

  const clearTabExperiments = useCallback((tabId) => {
    setExperimentsByTab((prev) =>
      prev.map((tab) =>
        tab.tabId === tabId ? { ...tab, experiments: {} } : tab
      )
    );
  }, []);

  const exportTabData = useCallback(
    (tabId) => {
      const tab = experimentsByTab.find((t) => t.tabId === tabId);
      return tab ? JSON.stringify(tab, null, 2) : null;
    },
    [experimentsByTab]
  );

  const importTabData = useCallback((tabData) => {
    try {
      const parsed = typeof tabData === 'string' ? JSON.parse(tabData) : tabData;
      if (!parsed.tabId || !parsed.tabName || !parsed.experiments) {
        throw new Error('Invalid tab data format');
      }

      setExperimentsByTab((prev) => [...prev, parsed]);
      return parsed.tabId;
    } catch (error) {
      console.error('[useExperimentsManager] Failed to import tab data:', error);
      return null;
    }
  }, []);

  const currentExperiments = useMemo(() => {
    if (enableMultiTab) {
      return getCurrentTabExperiments();
    }
    return singleTabExperiments;
  }, [enableMultiTab, singleTabExperiments, getCurrentTabExperiments]);

  const tabs = useMemo(() => {
    if (enableMultiTab) {
      return experimentsByTab;
    }
    return [
      {
        tabId: 'tab-default',
        tabName: 'Default',
        experiments: singleTabExperiments,
      },
    ];
  }, [enableMultiTab, singleTabExperiments, experimentsByTab]);

  const getTab = useCallback(
    (tabId) => {
      return experimentsByTab.find((t) => t.tabId === tabId) || null;
    },
    [experimentsByTab]
  );

  const countCriteriaUsage = useCallback(
    (criteriaId) => {
      let count = 0;
      Object.values(currentExperiments).forEach((criteriaList) => {
        if (criteriaList?.some((c) => c.id === criteriaId)) {
          count++;
        }
      });
      return count;
    },
    [currentExperiments]
  );

  const getRowCriteria = useCallback(
    (rowId) => {
      return currentExperiments[rowId] || [];
    },
    [currentExperiments]
  );

  return {
    currentExperiments,
    singleTabExperiments,
    experimentsByTab,
    activeTabId,
    tabs,

    addCriteriaToRow,
    removeCriteriaFromRow,
    addCriteriaToAllRows,
    setRowCriteria,
    clearAllExperiments,

    setActiveTabId,
    addTab,
    removeTab,
    renameTab,
    duplicateTab,
    clearTabExperiments,
    exportTabData,
    importTabData,
    addCriteriaToTabRow,
    removeCriteriaFromTabRow,
    addCriteriaToTabAllRows,
    setTabRowCriteria,
    getTabExperiments,
    getCurrentTabExperiments,
    getTab,

    setSingleTabExperiments,
    setExperimentsByTab,
    countCriteriaUsage,
    getRowCriteria,
  };
}

export default useExperimentsManager;
