import React, { useState } from 'react';
import './AddTaskModal.css';

const AddTaskModal = ({ open, onSave, onCancel, existingTasks = [] }) => {
  const [taskName, setTaskName] = useState('');
  const [taskDescription, setTaskDescription] = useState('');
  const [targetUrl, setTargetUrl] = useState('');
  const [errors, setErrors] = useState({});

  React.useEffect(() => {
    if (open) {
      setTaskName('');
      setTaskDescription('');
      setTargetUrl('');
      setErrors({});
    }
  }, [open]);

  if (!open) return null;

  const handleSave = (e) => {
    e.preventDefault();
    const nextErrors = {};

    if (!taskName.trim()) {
      nextErrors.taskName = 'Task name is required.';
    }

    if (!taskDescription.trim()) {
      nextErrors.taskDescription = 'Task description is required.';
    }

    if (!targetUrl.trim()) {
      nextErrors.targetUrl = 'Target URL is required.';
    }

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    if (onSave) {
      onSave({
        name: taskName.trim(),
        description: taskDescription.trim(),
        url: targetUrl.trim(),
      });
    }
  };

  return (
    <div className="add-task-modal-overlay" role="dialog" aria-modal="true">
      <div className="add-task-modal">
        <header className="add-task-modal__header">
          <h3 className="add-task-modal__title">Add Task</h3>
        </header>
        <form className="add-task-modal__body" onSubmit={handleSave}>
          <label className="add-task-field">
            <span className="add-task-field__label">Task Name</span>
            <input
              className="add-task-input"
              type="text"
              value={taskName}
              onChange={(e) => {
                setTaskName(e.target.value);
                if (errors.taskName) {
                  setErrors((prev) => ({ ...prev, taskName: '' }));
                }
              }}
              placeholder="e.g., Buy a product"
              autoFocus
            />
            {errors.taskName && (
              <span className="add-task-field__error">{errors.taskName}</span>
            )}
          </label>

          <label className="add-task-field">
            <span className="add-task-field__label">Task Description</span>
            <textarea
              className="add-task-textarea"
              value={taskDescription}
              onChange={(e) => {
                setTaskDescription(e.target.value);
                if (errors.taskDescription) {
                  setErrors((prev) => ({ ...prev, taskDescription: '' }));
                }
              }}
              placeholder="Describe what the agent should do..."
              rows={4}
            />
            {errors.taskDescription && (
              <span className="add-task-field__error">{errors.taskDescription}</span>
            )}
          </label>

          <label className="add-task-field">
            <span className="add-task-field__label">Target URL</span>
            <select
              className="add-task-input"
              value={targetUrl}
              onChange={(e) => {
                setTargetUrl(e.target.value);
                if (errors.targetUrl) {
                  setErrors((prev) => ({ ...prev, targetUrl: '' }));
                }
              }}
            >
              <option value="">Select a target</option>
              <option value="http://localhost:3000/riverbuy">RiverBuy</option>
              <option value="http://localhost:3000/zoomcar">ZoomCar</option>
              <option value="http://localhost:3000/dwellio">Dwellio</option>
            </select>
            {errors.targetUrl && (
              <span className="add-task-field__error">{errors.targetUrl}</span>
            )}
          </label>

          <div className="add-task-modal__actions">
            <button type="button" className="add-task-btn add-task-btn--muted" onClick={onCancel}>
              Cancel
            </button>
            <button type="submit" className="add-task-btn add-task-btn--primary">
              Add Task
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AddTaskModal;

