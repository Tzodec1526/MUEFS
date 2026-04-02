import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { listFavorites, removeFavorite, FavoriteCase } from '../../api/favorites';

function Favorites() {
  const [favorites, setFavorites] = useState<FavoriteCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [removing, setRemoving] = useState<number | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const data = await listFavorites();
        setFavorites(data.favorites);
      } catch {
        setFavorites([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleRemove = async (caseId: number) => {
    setRemoving(caseId);
    try {
      await removeFavorite(caseId);
      setFavorites(prev => prev.filter(f => f.case_id !== caseId));
    } catch {
      // ignore
    } finally {
      setRemoving(null);
    }
  };

  return (
    <div className="favorites-page">
      <div className="page-header">
        <h2>Favorite Cases</h2>
        <Link to="/cases/search" className="btn btn-secondary">Search Cases</Link>
      </div>
      <p className="info-text">
        Your bookmarked cases for quick access. Add cases from the Case Search page
        by clicking the star icon.
      </p>

      {loading && <p className="loading">Loading favorites...</p>}

      {!loading && favorites.length === 0 && (
        <div className="empty-state">
          <h3>No favorite cases yet</h3>
          <p>Search for a case and click the star to add it to your favorites.</p>
          <Link to="/cases/search" className="btn btn-primary">Search Cases</Link>
        </div>
      )}

      {!loading && favorites.length > 0 && (
        <div className="favorites-list">
          {favorites.map((fav) => (
            <div key={fav.id} className="favorite-card">
              <div className="favorite-card-star">&#9733;</div>
              <div className="favorite-card-body">
                <div className="favorite-card-header">
                  <h4>{fav.case_title || 'Untitled Case'}</h4>
                  <span className="favorite-card-number">{fav.case_number || `Case #${fav.case_id}`}</span>
                </div>
                {fav.notes && <p className="favorite-card-notes">{fav.notes}</p>}
                <span className="favorite-card-date">
                  Added {new Date(fav.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="favorite-card-actions">
                <Link to={`/cases/${fav.case_id}`} className="btn btn-secondary btn-small">
                  View Case
                </Link>
                <button
                  className="btn btn-danger btn-small"
                  onClick={() => handleRemove(fav.case_id)}
                  disabled={removing === fav.case_id}
                >
                  {removing === fav.case_id ? 'Removing...' : 'Remove'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default Favorites;
