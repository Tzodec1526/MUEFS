import { useState } from 'react';

interface ServiceContact {
  name: string;
  email: string;
  method: string;
}

interface Props {
  contacts: ServiceContact[];
  onChange: (contacts: ServiceContact[]) => void;
}

function ServiceList({ contacts, onChange }: Props) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [method, setMethod] = useState('electronic');

  const addContact = () => {
    if (!name.trim() || !email.trim()) return;
    onChange([...contacts, { name, email, method }]);
    setName('');
    setEmail('');
  };

  const removeContact = (index: number) => {
    onChange(contacts.filter((_, i) => i !== index));
  };

  return (
    <div className="form-section">
      <h3>Service of Process</h3>
      <p className="info-text">
        Add parties who should receive electronic service of this filing.
        Per MCR 1.109, all registered parties must be served electronically.
        Non-registered users must be served via traditional methods (mail, hand delivery).
      </p>

      <div className="service-form">
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="contactName">Name</label>
            <input
              id="contactName"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Attorney/Party name"
            />
          </div>
          <div className="form-group">
            <label htmlFor="contactEmail">Email</label>
            <input
              id="contactEmail"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="service@example.com"
            />
          </div>
          <div className="form-group">
            <label htmlFor="contactMethod">Method</label>
            <select
              id="contactMethod"
              value={method}
              onChange={(e) => setMethod(e.target.value)}
            >
              <option value="electronic">Electronic</option>
              <option value="mail">U.S. Mail</option>
              <option value="hand_delivery">Hand Delivery</option>
            </select>
          </div>
          <button className="btn btn-primary" onClick={addContact}>
            Add
          </button>
        </div>
      </div>

      {contacts.length > 0 && (
        <table className="service-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Method</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {contacts.map((contact, index) => (
              <tr key={index}>
                <td>{contact.name}</td>
                <td>{contact.email}</td>
                <td>{contact.method}</td>
                <td>
                  <button
                    className="btn btn-small btn-danger"
                    onClick={() => removeContact(index)}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default ServiceList;
