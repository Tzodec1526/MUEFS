import { useState, useEffect } from 'react';
import { listCourts, Court } from '../../api/courts';
import { needsErrorMessage } from '../../api/client';
import { listFavoriteCourts, addFavoriteCourt, removeFavoriteCourt } from '../../api/favorites';
import LoadError from '../common/LoadError';
import { useToast } from '../common/Toast';

interface Props {
  selectedCourtId: number | null;
  onSelect: (courtId: number, courtName: string) => void;
}

const MICHIGAN_COUNTIES = [
  'Alcona', 'Alger', 'Allegan', 'Alpena', 'Antrim', 'Arenac', 'Baraga', 'Barry',
  'Bay', 'Benzie', 'Berrien', 'Branch', 'Calhoun', 'Cass', 'Charlevoix', 'Cheboygan',
  'Chippewa', 'Clare', 'Clinton', 'Crawford', 'Delta', 'Dickinson', 'Eaton', 'Emmet',
  'Genesee', 'Gladwin', 'Gogebic', 'Grand Traverse', 'Gratiot', 'Hillsdale', 'Houghton',
  'Huron', 'Ingham', 'Ionia', 'Iosco', 'Iron', 'Isabella', 'Jackson', 'Kalamazoo',
  'Kalkaska', 'Kent', 'Keweenaw', 'Lake', 'Lapeer', 'Leelanau', 'Lenawee', 'Livingston',
  'Luce', 'Mackinac', 'Macomb', 'Manistee', 'Marquette', 'Mason', 'Mecosta', 'Menominee',
  'Midland', 'Missaukee', 'Monroe', 'Montcalm', 'Montmorency', 'Muskegon', 'Newaygo',
  'Oakland', 'Oceana', 'Ogemaw', 'Ontonagon', 'Osceola', 'Oscoda', 'Otsego', 'Ottawa',
  'Presque Isle', 'Roscommon', 'Saginaw', 'Sanilac', 'Schoolcraft', 'Shiawassee',
  'St. Clair', 'St. Joseph', 'Tuscola', 'Van Buren', 'Washtenaw', 'Wayne', 'Wexford',
];

const COURT_TYPE_LABEL: Record<string, string> = {
  circuit: 'Circuit Court',
  district: 'District Court',
  probate: 'Probate Court',
  court_of_claims: 'Court of Claims',
  court_of_appeals: 'Court of Appeals',
  supreme_court: 'Supreme Court',
  municipal: 'Municipal Court',
};
const APPELLATE_TYPES = new Set(['court_of_claims', 'court_of_appeals', 'supreme_court']);

function CourtSelector({ selectedCourtId, onSelect }: Props) {
  const { pushToast } = useToast();
  const [trialCourts, setTrialCourts] = useState<Court[]>([]);
  const [statewideCourts, setStatewideCourts] = useState<Court[]>([]);
  const [search, setSearch] = useState('');
  const [countyFilter, setCountyFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statewideFailed, setStatewideFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [favoritedCourtIds, setFavoritedCourtIds] = useState<Set<number>>(() => new Set());
  const [togglingFav, setTogglingFav] = useState<number | null>(null);

  // Statewide/appellate forums (Court of Appeals, Supreme Court, Court of Claims) apply
  // regardless of county -- load them once and always surface them in their own group so
  // they are never buried under a county filter.
  useEffect(() => {
    const controller = new AbortController();
    listCourts({ tier: 'appellate', page_size: 50 }, controller.signal)
      .then((r) => { setStatewideCourts(r.courts); setStatewideFailed(false); })
      .catch(() => { if (!controller.signal.aborted) setStatewideFailed(true); });
    return () => controller.abort();
  }, [reloadKey]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await listCourts({
          tier: 'trial',
          county: countyFilter || undefined,
          court_type: typeFilter || undefined,
          q: search.trim() || undefined,
          page_size: 100,
          page,
        }, controller.signal);
        setTrialCourts(result.courts);
        setTotal(result.total);
      } catch {
        if (controller.signal.aborted) return;
        setError("We couldn't load the court list. Please try again.");
        setTrialCourts([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 300);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [countyFilter, typeFilter, search, reloadKey, page]);

  useEffect(() => {
    async function loadFavorites() {
      try {
        const data = await listFavoriteCourts();
        setFavoritedCourtIds(new Set(data.favorites.map(f => f.court_id)));
      } catch {
        setFavoritedCourtIds(new Set());
      }
    }
    loadFavorites();
  }, []);

  const toggleFavoriteCourt = async (courtId: number) => {
    setTogglingFav(courtId);
    try {
      if (favoritedCourtIds.has(courtId)) {
        await removeFavoriteCourt(courtId);
        setFavoritedCourtIds(prev => {
          const next = new Set(prev);
          next.delete(courtId);
          return next;
        });
      } else {
        await addFavoriteCourt(courtId);
        setFavoritedCourtIds(prev => new Set(prev).add(courtId));
      }
    } catch (err) {
      if (needsErrorMessage(err)) pushToast('Could not update the favorite court. Please try again.', 'error');
    } finally {
      setTogglingFav(null);
    }
  };

  // The statewide group is small; filter it client-side by search + type. County filter
  // does NOT hide it (these courts have statewide jurisdiction).
  const q = search.trim().toLowerCase();
  const visibleStatewide = statewideCourts.filter((c) =>
    (!typeFilter || c.court_type === typeFilter) &&
    (!q || c.name.toLowerCase().includes(q) || (c.city || '').toLowerCase().includes(q))
  );

  const sortByFav = (list: Court[]) => [...list].sort((a, b) => {
    const aFav = favoritedCourtIds.has(a.id) ? 1 : 0;
    const bFav = favoritedCourtIds.has(b.id) ? 1 : 0;
    if (aFav !== bFav) return bFav - aFav;
    return a.name.localeCompare(b.name);
  });

  const renderCard = (court: Court) => {
    const isFav = favoritedCourtIds.has(court.id);
    const isAppellate = APPELLATE_TYPES.has(court.court_type);
    const typeLabel = COURT_TYPE_LABEL[court.court_type] || court.court_type;
    const detailsId = `court-card-${court.id}-details`;
    const addressId = `court-card-${court.id}-address`;
    // Selecting and starring are sibling buttons; the select button's click area covers the card.
    return (
      <div key={court.id} className={`court-card ${selectedCourtId === court.id ? 'selected' : ''}`}>
        <div className="court-card-head">
          <h4>
            <button
              type="button"
              className="court-card-select"
              onClick={() => onSelect(court.id, court.name)}
              aria-pressed={selectedCourtId === court.id}
              aria-describedby={court.address ? `${detailsId} ${addressId}` : detailsId}
            >
              {court.name}
            </button>
          </h4>
          <button
            type="button"
            className={`fav-star ${isFav ? 'active' : ''}`}
            onClick={() => toggleFavoriteCourt(court.id)}
            disabled={togglingFav !== null}
            title={isFav ? 'Remove from favorites' : 'Add to favorites'}
            aria-label={isFav ? `Remove ${court.name} from favorites` : `Add ${court.name} to favorites`}
          >
            {isFav ? '★' : '☆'}
          </button>
        </div>
        <p id={detailsId}>
          {isAppellate ? 'Statewide jurisdiction' : `${court.county} County`} &middot; {typeLabel}
        </p>
        {court.address && <p id={addressId} className="court-address">{court.address}</p>}
      </div>
    );
  };

  return (
    <div className="form-section">
      <h3>Select Court</h3>
      <p className="info-text">
        Search by court name, or browse by county. Statewide and appellate courts (Court of Appeals,
        Supreme Court, Court of Claims) are listed in their own group below.
      </p>

      <div className="form-group">
        <label htmlFor="courtSearch">Search courts</label>
        <input
          id="courtSearch"
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder="e.g., Court of Appeals, Oakland, 3rd Circuit"
        />
      </div>

      <div className="filter-row">
        <div className="form-group">
          <label htmlFor="county">County</label>
          <select id="county" value={countyFilter} onChange={(e) => { setCountyFilter(e.target.value); setPage(1); }}>
            <option value="">All Counties</option>
            {MICHIGAN_COUNTIES.map((county) => (
              <option key={county} value={county}>{county}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="courtType">Court Type</label>
          <select id="courtType" value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}>
            <option value="">All Types</option>
            <option value="circuit">Circuit Court</option>
            <option value="district">District Court</option>
            <option value="probate">Probate Court</option>
            <option value="court_of_claims">Court of Claims</option>
            <option value="court_of_appeals">Court of Appeals</option>
            <option value="supreme_court">Supreme Court</option>
          </select>
        </div>
      </div>

      {error || statewideFailed ? (
        // Missing appellate courts would otherwise look like an empty statewide list.
        <LoadError message={error || "We couldn't load the statewide and appellate courts. Please try again."}
          onRetry={() => setReloadKey((k) => k + 1)} />
      ) : (
        <>
          {visibleStatewide.length > 0 && (
            <div className="court-group">
              <h4 className="court-group-title">Statewide &amp; Appellate Courts</h4>
              <div className="court-list">{sortByFav(visibleStatewide).map(renderCard)}</div>
            </div>
          )}
          <div className="court-group">
            <h4 className="court-group-title">Trial Courts</h4>
            {loading && <p>Loading courts…</p>}
            <div className="court-list">
              {sortByFav(trialCourts).map(renderCard)}
              {!loading && trialCourts.length === 0 && (
                <p className="no-results">
                  No trial courts match. Try a different county or search term.
                </p>
              )}
            </div>
            {total > 100 && (
              <nav className="pagination" aria-label="Trial court pages">
                <button className="btn btn-secondary" disabled={loading || page === 1} onClick={() => setPage(p => p - 1)}>Previous</button>
                <span>Page {page} of {Math.ceil(total / 100)}</span>
                <button className="btn btn-secondary" disabled={loading || page * 100 >= total} onClick={() => setPage(p => p + 1)}>Next</button>
              </nav>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default CourtSelector;
