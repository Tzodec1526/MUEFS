import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { listFavorites, removeFavorite, FavoriteCase, listFavoriteCourts, removeFavoriteCourt, FavoriteCourt } from '../../api/favorites';

function Favorites() {
  const [caseFavorites, setCaseFavorites] = useState<FavoriteCase[]>([]);
  const [courtFavorites, setCourtFavorites] = useState<FavoriteCourt[]>([]);
  const [loading, setLoading] = useState(true);
  const [removingCase, setRemovingCase] = useState<number | null>(null);
  const [removingCourt, setRemovingCourt] = useState<number | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [casesData, courtsData] = await Promise.all([
          listFavorites(),
          listFavoriteCourts(),
        ]);
        setCaseFavorites(casesData.favorites);
        setCourtFavorites(courtsData.favorites);
      } catch {
        setCaseFavorites([]);
        setCourtFavorites([]);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleRemoveCase = async (caseId: number) => {
    setRemovingCase(caseId);
    try {
      await removeFavorite(caseId);
      setCaseFavorites(prev => prev.filter(f => f.case_id !== caseId));
    } catch {
      // ignore
    } finally {
      setRemovingCase(null);
    }
  };

  const handleRemoveCourt = async (courtId: number) => {
    setRemovingCourt(courtId);
    try {
      await removeFavoriteCourt(courtId);
      setCourtFavorites(prev => prev.filter(f => f.court_id !== courtId));
    } catch {
      // ignore
    } finally {
      setRemovingCourt(null);
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

      {!loading && caseFavorites.length === 0 && (
        <div className="empty-state">
          <h3>No favorite cases yet</h3>
          <p>Search for a case and click the star to add it to your favorites.</p>
          <Link to="/cases/search" className="btn btn-primary">Search Cases</Link>
        </div>
      )}

      {!loading && caseFavorites.length > 0 && (
        <div className="favorites-list">
          {caseFavorites.map((fav) => (
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
                  onClick={() => handleRemoveCase(fav.case_id)}
                  disabled={removingCase === fav.case_id}
                >
                  {removingCase === fav.case_id ? 'Removing...' : 'Remove'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="page-header" style={{ marginTop: '2rem' }}>
        <h2>Favorite Courts</h2>
        <Link to="/filing/new" className="btn btn-secondary">New Filing</Link>
      </div>
      <p className="info-text">
        Your frequently used courts (attorneys often practice across many). Star courts in the court selector during filing.
      </p>

      {!loading && courtFavorites.length === 0 && (
        <div className="empty-state">
          <h3>No favorite courts yet</h3>
          <p>When filing, use the court selector and star your common courts for quick access.</p>
          <Link to="/filing/new" className="btn btn-primary">Start a Filing</Link>
        </div>
      )}

      {!loading && courtFavorites.length > 0 && (
        <div className="favorites-list">
          {courtFavorites.map((fav) => (
            <div key={fav.id} className="favorite-card">
              <div className="favorite-card-star">&#9733;</div>
              <div className="favorite-card-body">
                <div className="favorite-card-header">
                  <h4>{fav.court_name || `Court #${fav.court_id}`}</h4>
                  <span className="favorite-card-number">{fav.county ? `${fav.county} County` : ''} {fav.court_type ? `| ${fav.court_type}` : ''}</span>
                </div>
                {fav.notes && <p className="favorite-card-notes">{fav.notes}</p>}
                <span className="favorite-card-date">
                  Added {new Date(fav.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="favorite-card-actions">
                <Link to={`/filing/new?court_id=${fav.court_id}`} className="btn btn-secondary btn-small">
                  Use for Filing
                </Link>
                <button
                  className="btn btn-danger btn-small"
                  onClick={() => handleRemoveCourt(fav.court_id)}
                  disabled={removingCourt === fav.court_id}
                >
                  {removingCourt === fav.court_id ? 'Removing...' : 'Remove'}
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
