import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { CatalogGroup } from "../types";

export default function Catalog() {
  const [groups, setGroups] = useState<CatalogGroup[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .get<CatalogGroup[]>("/api/portals/catalog")
      .then(setGroups)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="container muted">Loading catalog…</div>;

  const current = groups.find((g) => g.category === selected);

  return (
    <div className="container">
      <h1>How can we help?</h1>
      <p className="subtitle">
        {selected
          ? "Choose a request type below."
          : "Pick a category to see the available request portals."}
      </p>

      {!selected && (
        <>
          {groups.length === 0 && (
            <div className="empty">No portals are available yet. Check back soon.</div>
          )}
          <div className="grid">
            {groups.map((g) => (
              <div key={g.category} className="tile" onClick={() => setSelected(g.category)}>
                <h3>{g.category}</h3>
                <p>{g.portals.length} request type{g.portals.length === 1 ? "" : "s"}</p>
                <div className="count">Browse →</div>
              </div>
            ))}
          </div>
        </>
      )}

      {selected && current && (
        <>
          <div className="breadcrumb">
            <a onClick={() => setSelected(null)} style={{ cursor: "pointer" }}>
              ← All categories
            </a>{" "}
            / {current.category}
          </div>
          <div className="grid">
            {current.portals.map((p) => (
              <div
                key={p.id}
                className="tile"
                onClick={() => navigate(`/portals/${p.slug}`)}
              >
                <h3>{p.name}</h3>
                <p>{p.description || "Submit a request"}</p>
                <div className="count">Open form →</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
