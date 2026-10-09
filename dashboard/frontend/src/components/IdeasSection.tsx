import { useState, useEffect } from 'react';
import type { Idea } from '../types';
import { fetchIdeas, createIdea, updateIdea, deleteIdea } from '../api';
import { useRequest } from '../hooks/useRequest';
import { IdeaCard } from './IdeaCard';
import './IdeasSection.css';

export function IdeasSection() {
    const request = useRequest(fetchIdeas, []);
    const { loading, error: loadError, reload: loadIdeas } = request;
    const ideas: Idea[] = request.data ?? [];
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [editingIdea, setEditingIdea] = useState<Idea | null>(null);
    const [ideaText, setIdeaText] = useState('');
    const [saveError, setSaveError] = useState<string | null>(null);
    const [clearedLoadError, setClearedLoadError] = useState<Error | null>(null);

    // A failed load shows in the same slot as a failed save, until the next
    // successful save or a close clears it.
    const error = saveError ?? (loadError && loadError !== clearedLoadError ? loadError.message || 'Failed to load ideas' : null);
    const setError = (message: string | null) => {
        setSaveError(message);
        if (message === null) setClearedLoadError(loadError);
    };

    useEffect(() => {
        if (loadError) console.error('Failed to load ideas:', loadError);
    }, [loadError]);

    const handleCreate = async () => {
        if (!ideaText.trim()) {
            setError('Idea text cannot be empty');
            return;
        }

        try {
            await createIdea(ideaText);
            setIdeaText('');
            setShowCreateModal(false);
            setError(null);
            loadIdeas();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create idea');
        }
    };

    const handleUpdate = async () => {
        if (!editingIdea || !ideaText.trim()) {
            setError('Idea text cannot be empty');
            return;
        }

        try {
            await updateIdea(editingIdea.id, ideaText);
            setIdeaText('');
            setEditingIdea(null);
            setError(null);
            loadIdeas();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to update idea');
        }
    };

    const handleDelete = async (ideaId: string) => {
        try {
            await deleteIdea(ideaId);
            loadIdeas();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to delete idea');
        }
    };

    const openEditModal = (idea: Idea) => {
        setEditingIdea(idea);
        setIdeaText(idea.text);
        setError(null);
    };

    const closeModal = () => {
        setShowCreateModal(false);
        setEditingIdea(null);
        setIdeaText('');
        setError(null);
    };

    if (loading) {
        return <div className="ideas-section-loading">Loading ideas...</div>;
    }

    return (
        <div className="ideas-section">
            <div className="ideas-header">
                <h2>Ideas</h2>
                <button onClick={() => setShowCreateModal(true)} className="create-idea-btn">
                    + Create Idea
                </button>
            </div>

            {ideas.length === 0 ? (
                <div className="ideas-empty">
                    No ideas yet. Click "Create Idea" to add your first pre-project thought.
                </div>
            ) : (
                <div className="ideas-list">
                    {ideas.map((idea) => (
                        <IdeaCard
                            key={idea.id}
                            idea={idea}
                            onEdit={openEditModal}
                            onDelete={handleDelete}
                        />
                    ))}
                </div>
            )}

            {(showCreateModal || editingIdea) && (
                <div className="modal-overlay" onClick={closeModal}>
                    <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                        <h3>{editingIdea ? 'Edit Idea' : 'Create New Idea'}</h3>
                        <textarea
                            className="idea-textarea"
                            value={ideaText}
                            onChange={(e) => setIdeaText(e.target.value)}
                            placeholder="Enter your idea..."
                            rows={10}
                            autoFocus
                        />
                        {error && <div className="idea-error">{error}</div>}
                        <div className="modal-actions">
                            <button onClick={closeModal} className="cancel-btn">
                                Cancel
                            </button>
                            <button
                                onClick={editingIdea ? handleUpdate : handleCreate}
                                className="save-btn"
                            >
                                {editingIdea ? 'Update' : 'Create'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
