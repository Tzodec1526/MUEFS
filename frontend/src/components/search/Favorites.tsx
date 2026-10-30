import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { listFavorites, removeFavorite, FavoriteCase, listFavoriteCourts, removeFavoriteCourt, FavoriteCourt } from '../../api/favorites';
import { formatShortDate } from '../../utils/format';
import { actionErrorMessage } from '../../api/client';
import LoadError from '../common/LoadError';
import { loadFailure, type LoadFailure } from '../../utils/errors';
import { useToast } from '../common/Toast';
import { usePageTitle } from '../../utils/pageTitle';
import PageHeading from '../common/PageHeading';

function Favorites() {
  usePageTitle('Favorites');
  const { pushToast } = useToast();
  const [caseFavorites, setCaseFavorites] = useState<FavoriteCase[]>([]);
  const [courtFavorites, setCourtFavorites] = useState<FavoriteCourt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<LoadFailure | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [removingCase, setRemovingCase] = useState<number | null>(null);
  const [removingCourt, setRemovingCourt] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [casesData, courtsData] = await Promise.all([
          listFavorites(),
          listFavoriteCourts(),
        ]);
        if (!active) return;
        setCaseFavorites(casesData.favorites);
        setCourtFavorites(courtsData.favorites);
      } catch (err) {
        if (active) setError(loadFailure(err, 'Could not load your favorites. Please try again.'));
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, [attempt]);

  const handleRemoveCase = async (caseId: number) => {
    setRemovingCase(caseId);
    try {
      await removeFavorite(caseId);
      setCaseFavorites(prev => prev.filter(f => f.case_id !== caseId));
    } catch (err) {
      const message = actionErrorMessage(err, 'Could not remove the favorite case. Please try again.');
      if (message) pushToast(message, 'error');
    } finally {
      setRemovingCase(null);
    }
  };

  const handleRemoveCourt = async (courtId: number) => {
    setRemovingCourt(courtId);
    try {
      await removeFavoriteCourt(courtId);
      setCourtFavorites(prev => prev.filter(f => f.court_id !== courtId));
    } catch (err) {
      const message = actionErrorMessage(err, 'Could not remove the favorite court. Please try again.');
      if (message) pushToast(message, 'error');
    } finally {
      setRemovingCourt(null);
    }
  };

  return (
    <div className="favorites-page">
      <PageHeading>Favorites</PageHeading>
      <div className="page-header">
        <h2>Favorite cases</h2>
        <Link to="/cases/search" className="btn btn-secondary">Search cases</Link>
      </div>
      <p className="info-text">
        Your saved cases. Add a case from Case search by clicking its star.
      </p>

      {loading && <p className="loading" role="status">Loading favorites...</p>}
      {error && <LoadError failure={error} onRetry={() => setAttempt(value => value + 1)} />}

      {!loading && !error && caseFavorites.length === 0 && (
        <div className="empty-state">
          <h3>No favorite cases yet</h3>
          <p>Search for a case and click the star to add it to your favorites.</p>
          <Link to="/cases/search" className="btn btn-primary">Search cases</Link>
        </div>
      )}

      {!loading && !error && caseFavorites.length > 0 && (
        <div className="favorites-list">
          {caseFavorites.map((fav) => (
            <div key={fav.id} className="favorite-card">
              <div className="favorite-card-star">&#9733;</div>
              <div className="favorite-card-body">
                <div className="favorite-card-header">
                  <h3>{fav.case_title || 'Untitled case'}</h3>
                  <span className="favorite-card-number">{fav.case_number || `Case #${fav.case_id}`}</span>
                </div>
                {fav.notes && <p className="favorite-card-notes">{fav.notes}</p>}
                <span className="favorite-card-date">
                  Added {formatShortDate(fav.created_at)}
                </span>
              </div>
              <div className="favorite-card-actions">
                <Link to={`/cases/${fav.case_id}`} className="btn btn-secondary btn-small">
                  View case
                </Link>
                <button
                  className="btn btn-danger btn-small"
                  onClick={() => handleRemoveCase(fav.case_id)}
                  disabled={removingCase !== null}
                >
                  {removingCase === fav.case_id ? 'Removing...' : 'Remove'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="page-header" style={{ marginTop: '2rem' }}>
        <h2>Favorite courts</h2>
        <Link to="/filing/new" className="btn btn-secondary">New filing</Link>
      </div>
      <p className="info-text">
        The courts you use most. Star a court in the court selector when you file.
      </p>

      {!loading && !error && courtFavorites.length === 0 && (
        <div className="empty-state">
          <h3>No favorite courts yet</h3>
          <p>When you file, star a court in the court selector.</p>
          <Link to="/filing/new" className="btn btn-primary">Start a filing</Link>
        </div>
      )}

      {!loading && !error && courtFavorites.length > 0 && (
        <div className="favorites-list">
          {courtFavorites.map((fav) => (
            <div key={fav.id} className="favorite-card">
              <div className="favorite-card-star">&#9733;</div>
              <div className="favorite-card-body">
                <div className="favorite-card-header">
                  <h3>{fav.court_name || `Court #${fav.court_id}`}</h3>
                  <span className="favorite-card-number">{fav.county ? `${fav.county} County` : ''} {fav.court_type ? `| ${fav.court_type}` : ''}</span>
                </div>
                {fav.notes && <p className="favorite-card-notes">{fav.notes}</p>}
                <span className="favorite-card-date">
                  Added {formatShortDate(fav.created_at)}
                </span>
              </div>
              <div className="favorite-card-actions">
                <Link to={`/filing/new?court_id=${fav.court_id}`} className="btn btn-secondary btn-small">
                  Use for filing
                </Link>
                <button
                  className="btn btn-danger btn-small"
                  onClick={() => handleRemoveCourt(fav.court_id)}
                  disabled={removingCourt !== null}
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
