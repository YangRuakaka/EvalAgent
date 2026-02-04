import React, { useState, useMemo } from 'react';
import PropTypes from 'prop-types';
import { useData } from '../../context/DataContext';
import './CriteriaManagerModal.css';

const generateRandomColor = () => {
    const letters = '0123456789ABCDEF';
    let color = '#';
    for (let i = 0; i < 6; i++) {
        color += letters[Math.floor(Math.random() * 16)];
    }
    return color;
};

const generateId = () => `crit_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

const CriteriaForm = ({ initialData, existingTitles = [], onSave, onCancel }) => {
    const [formData, setFormData] = useState(initialData || {
        title: '',
        description: '',
        assertion: '',
        // Color will be assigned on save for new items
    });

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        if (existingTitles.includes(formData.title.trim())) {
            alert('Criteria title must be unique.');
            return;
        }
        onSave(formData);
    };

    return (
        <form className="criteria-form" onSubmit={handleSubmit}>
            <div className="form-group">
                <label className="form-label">Title</label>
                <input
                    type="text"
                    name="title"
                    className="form-input"
                    value={formData.title}
                    onChange={handleChange}
                    required
                    placeholder="e.g. Safety Check"
                />
            </div>

            <div className="form-group">
                <label className="form-label">Description</label>
                <textarea
                    name="description"
                    className="form-textarea"
                    value={formData.description}
                    onChange={handleChange}
                    placeholder="Describe what this criteria evaluates..."
                />
            </div>

            <div className="form-group">
                <label className="form-label">Assertion / Prompt</label>
                <textarea
                    name="assertion"
                    className="form-textarea"
                    value={formData.assertion}
                    onChange={handleChange}
                    required
                    placeholder="The specific assertion or prompt for evaluation..."
                    style={{ fontFamily: 'monospace' }}
                />
            </div>

            <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={onCancel}>
                    Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                    {initialData ? 'Update Criteria' : 'Create Criteria'}
                </button>
            </div>
        </form>
    );
};

CriteriaForm.propTypes = {
    initialData: PropTypes.object,
    existingTitles: PropTypes.arrayOf(PropTypes.string),
    onSave: PropTypes.func.isRequired,
    onCancel: PropTypes.func.isRequired,
};

const CriteriaCard = ({ criteria, onEdit, onDelete }) => {
    const cardColor = criteria.color || '#3B82F6';

    return (
        <div className="manager-criteria-card" style={{ '--criteria-color': cardColor }}>
            <div 
                className="manager-criteria-card-color-strip" 
                style={{ backgroundColor: cardColor }} 
            />
            <div className="manager-criteria-card-header">
                <h3 className="manager-criteria-card-title">{criteria.title}</h3>
                <div className="manager-criteria-card-actions">
                    <button 
                        className="icon-btn" 
                        onClick={() => onEdit(criteria)}
                        title="Edit"
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                        </svg>
                    </button>
                    <button 
                        className="icon-btn delete" 
                        onClick={() => onDelete(criteria.id)}
                        title="Delete"
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>
            </div>
            <p className="manager-criteria-card-desc">{criteria.description || 'No description provided.'}</p>
            <div className="manager-criteria-card-assertion" title={criteria.assertion}>
                {criteria.assertion}
            </div>
        </div>
    );
};

CriteriaCard.propTypes = {
    criteria: PropTypes.object.isRequired,
    onEdit: PropTypes.func.isRequired,
    onDelete: PropTypes.func.isRequired,
};

const CriteriaManagerModal = ({ onClose }) => {
    const { state: { criterias }, addCriteria, updateCriteria, removeCriteria } = useData();
    const [view, setView] = useState('list'); // 'list' | 'form'
    const [editingId, setEditingId] = useState(null);

    const criteriaList = useMemo(() => Object.values(criterias || {}), [criterias]);

    const existingTitles = useMemo(() => 
        criteriaList
            .filter(c => c.id !== editingId)
            .map(c => c.title)
    , [criteriaList, editingId]);

    const handleSave = (formData) => {
        if (editingId) {
            updateCriteria({ ...formData, id: editingId });
        } else {
            addCriteria({ ...formData, id: generateId(), color: generateRandomColor() });
        }
        setView('list');
        setEditingId(null);
    };

    const handleEdit = (criteria) => {
        setEditingId(criteria.id);
        setView('form');
    };

    const handleDelete = (id) => {
        if (window.confirm('Are you sure you want to delete this criteria?')) {
            removeCriteria(id);
        }
    };

    const handleCancel = () => {
        setView('list');
        setEditingId(null);
    };

    const handleAddNew = () => {
        setEditingId(null);
        setView('form');
    };

    const editingCriteria = useMemo(() => 
        editingId ? criterias[editingId] : null
    , [criterias, editingId]);

    return (
        <div className="criteria-manager-overlay" onClick={onClose}>
            <div className="criteria-manager-content" onClick={e => e.stopPropagation()}>
                <div className="criteria-manager-header">
                    <h2 className="criteria-manager-title">
                        {view === 'list' ? 'Manage Criteria' : (editingId ? 'Edit Criteria' : 'New Criteria')}
                    </h2>
                    <button className="criteria-manager-close" onClick={onClose}>&times;</button>
                </div>
                
                <div className="criteria-manager-body">
                    {view === 'list' ? (
                        <>
                            <div className="criteria-list-controls">
                                <button className="btn btn-primary" onClick={handleAddNew}>
                                    + Add Criteria
                                </button>
                            </div>
                            
                            {criteriaList.length === 0 ? (
                                <div className="empty-state">
                                    <p>No criteria defined yet. Create one to get started.</p>
                                </div>
                            ) : (
                                <div className="criteria-grid">
                                    {criteriaList.map(crit => (
                                        <CriteriaCard 
                                            key={crit.id} 
                                            criteria={crit} 
                                            onEdit={handleEdit} 
                                            onDelete={handleDelete} 
                                        />
                                    ))}
                                </div>
                            )}
                        </>
                    ) : (
                        <CriteriaForm 
                            initialData={editingCriteria} 
                            existingTitles={existingTitles}
                            onSave={handleSave} 
                            onCancel={handleCancel} 
                        />
                    )}
                </div>
            </div>
        </div>
    );
};

CriteriaManagerModal.propTypes = {
    onClose: PropTypes.func.isRequired,
};

export default CriteriaManagerModal;
