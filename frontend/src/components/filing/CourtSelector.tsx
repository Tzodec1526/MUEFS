import { useState, useEffect, useRef } from 'react';
import { listCourts, Court } from '../../api/courts';
import { listFavoriteCourts, addFavoriteCourt, removeFavoriteCourt } from '../../api/favorites';
import LoadError from '../common/LoadError';

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
  const [trialCourts, setTrialCourts] = useState<Court[]>([]);
  const [statewideCourts, setStatewideCourts] = useState<Court[]>([]);
  const [search, setSearch] = useState('');
  const [countyFilter, setCountyFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [favoritedCourtIds, setFavoritedCourtIds] = useState<Set<number>>(new Set());
  const [togglingFav, setTogglingFav] = useState<number | null>(null);
  const showFavorites = true;

  // Statewide/appellate forums (Court of Appeals, Supreme Court, Court of Claims) apply
  // regardless of county -- load them once and always surface them in their own group so
  // they are never buried under a county filter.
  useEffect(() => {
    listCourts({ tier: 'appellate', page_size: 50 })
      .then((r) => setStatewideCourts(r.courts))
      .catch(() => setStatewideCourts([]));
  }, []);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await listCourts({
          tier: 'trial',
          county: countyFilter || undefined,
          court_type: typeFilter || undefined,
          q: search.trim() || undefined,
          page_size: 100,
        });
        setTrialCourts(result.courts);
      } catch {
        setError("We couldn't load the court list. Please try again.");
        setTrialCourts([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [countyFilter, typeFilter, search, reloadKey]);

  useEffect(() => {
    if (!showFavorites) return;
    async function loadFavorites() {
      try {
        const data = await listFavoriteCourts();
        setFavoritedCourtIds(new Set(data.favorites.map(f => f.court_id)));
      } catch {
        setFavoritedCourtIds(new Set());
      }
    }
    loadFavorites();
  }, [showFavorites]);

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
    } catch {
      // ignore errors for demo
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
    return (
      <div
        key={court.id}
        className={`court-card ${selectedCourtId === court.id ? 'selected' : ''}`}
        role="button"
        tabIndex={0}
        onClick={() => onSelect(court.id, court.name)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(court.id, court.name); }
        }}
      >
        <div className="court-card-head">
          <h4>{court.name}</h4>
          {showFavorites && (
            <button
              className={`fav-star ${isFav ? 'active' : ''}`}
              onClick={(e) => { e.stopPropagation(); toggleFavoriteCourt(court.id); }}
              disabled={togglingFav === court.id}
              title={isFav ? 'Remove from favorites' : 'Add to favorites'}
              aria-label={isFav ? 'Remove court from favorites' : 'Add court to favorites'}
            >
              {isFav ? '★' : '☆'}
            </button>
          )}
        </div>
        <p>
          {isAppellate ? 'Statewide jurisdiction' : `${court.county} County`} &middot; {typeLabel}
        </p>
        {court.address && <p className="court-address">{court.address}</p>}
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
          onChange={(e) => setSearch(e.target.value)}
          placeholder="e.g., Court of Appeals, Oakland, 3rd Circuit"
        />
      </div>

      <div className="filter-row">
        <div className="form-group">
          <label htmlFor="county">County</label>
          <select id="county" value={countyFilter} onChange={(e) => setCountyFilter(e.target.value)}>
            <option value="">All Counties</option>
            {MICHIGAN_COUNTIES.map((county) => (
              <option key={county} value={county}>{county}</option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="courtType">Court Type</label>
          <select id="courtType" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
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

      {error ? (
        <LoadError message={error} onRetry={() => setReloadKey((k) => k + 1)} />
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
          </div>
        </>
      )}
    </div>
  );
}

export default CourtSelector;
