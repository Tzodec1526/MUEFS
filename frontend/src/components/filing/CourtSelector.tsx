import { useState, useEffect, useRef } from 'react';
import { listCourts, Court } from '../../api/courts';

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

function CourtSelector({ selectedCourtId, onSelect }: Props) {
  const [courts, setCourts] = useState<Court[]>([]);
  const [countyFilter, setCountyFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [loading, setLoading] = useState(false);

  // Debounce filter changes to avoid excessive API calls
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const result = await listCourts({
          county: countyFilter || undefined,
          court_type: typeFilter || undefined,
        });
        setCourts(result.courts);
      } catch {
        setCourts([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [countyFilter, typeFilter]);

  return (
    <div className="form-section">
      <h3>Select Court</h3>
      <p className="info-text">
        Choose the Michigan court where you want to file your documents.
      </p>

      <div className="filter-row">
        <div className="form-group">
          <label htmlFor="county">County</label>
          <select
            id="county"
            value={countyFilter}
            onChange={(e) => setCountyFilter(e.target.value)}
          >
            <option value="">All Counties</option>
            {MICHIGAN_COUNTIES.map((county) => (
              <option key={county} value={county}>
                {county}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="courtType">Court Type</label>
          <select
            id="courtType"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
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

      {loading && <p>Loading courts...</p>}

      <div className="court-list">
        {courts.map((court) => (
          <div
            key={court.id}
            className={`court-card ${selectedCourtId === court.id ? 'selected' : ''}`}
            onClick={() => onSelect(court.id, court.name)}
          >
            <h4>{court.name}</h4>
            <p>
              {court.county} County | {court.court_type.replace('_', ' ')}
            </p>
            {court.address && <p className="court-address">{court.address}</p>}
          </div>
        ))}
        {!loading && courts.length === 0 && (
          <p className="no-results">
            No courts found. Try adjusting your filters.
          </p>
        )}
      </div>
    </div>
  );
}

export default CourtSelector;
