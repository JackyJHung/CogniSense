import { useEffect, useState } from "react";
import { Leaf } from "lucide-react";
import { Shell } from "@/components/Shell";
import { GroupedList, ListRow } from "@/components/ui/List";
import { Disclaimer } from "@/components/Disclaimer";
import { api, type DailySuggestions } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export function SuggestionsPage() {
  const { user } = useAuth();
  const [data, setData] = useState<DailySuggestions | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    api
      .get<DailySuggestions>(`/reports/daily-suggestions/${user.id}`)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  }, [user]);

  if (!user) return null;

  return (
    <Shell
      title="Daily suggestions"
      back={{ to: "/dashboard", label: "Today" }}
      subtitle="Tailored to your life stage from the Lancet 2024 modifiable-risk-factor framework."
    >
      {error && <p className="mb-4 px-1 text-subhead text-danger">{error}</p>}
      {!data ? (
        <div className="space-y-px overflow-hidden rounded-2xl" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 animate-pulse bg-fill-2" />
          ))}
        </div>
      ) : (
        <GroupedList footer={data.lancet_risk_factor_source}>
          {data.suggestions.map((s, i) => {
            const colon = s.indexOf(":");
            return (
              <ListRow
                key={i}
                icon={Leaf}
                tone="green"
                title={colon > 0 ? s.slice(0, colon) : s}
                subtitle={colon > 0 ? s.slice(colon + 1).trim() : undefined}
              />
            );
          })}
        </GroupedList>
      )}

      <Disclaimer />
    </Shell>
  );
}
