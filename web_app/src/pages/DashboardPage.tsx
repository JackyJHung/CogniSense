import { ChartLine, ListChecks, Moon, Sparkles, Sun, Sunrise } from "lucide-react";
import { Shell } from "@/components/Shell";
import { GroupedList, ListRow } from "@/components/ui/List";
import { Disclaimer } from "@/components/Disclaimer";
import { useAuth } from "@/lib/auth";

function greeting(hour: number): string {
  if (hour < 5) return "Hello";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

const TODAY = new Intl.DateTimeFormat(undefined, { weekday: "long", month: "long", day: "numeric" });

/* Today, laid out like iOS Settings: the day's three check-ins first, then
 * what they add up to, then the memory aid. */
export function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;
  const now = new Date();

  return (
    <Shell
      title="Today"
      eyebrow={TODAY.format(now)}
      subtitle={`${greeting(now.getHours())}, ${user.username}.`}
    >
      <GroupedList header="Check-ins">
        <ListRow
          to="/morning"
          icon={Sunrise}
          tone="orange"
          title="Morning check-in"
          subtitle="Log today's plans and see five things to remember."
        />
        <ListRow
          to="/midday"
          icon={Sun}
          tone="yellow"
          title="Midday check-in"
          subtitle="A quick, ungraded recall of your day so far."
        />
        <ListRow
          to="/evening"
          icon={Moon}
          tone="indigo"
          title="Evening check-in"
          subtitle="Recall today, then name this morning's objects."
        />
      </GroupedList>

      <GroupedList header="Insights">
        <ListRow
          to="/report"
          icon={ChartLine}
          tone="pink"
          title="Risk report"
          subtitle="Your trend, with honest ranges, and peer benchmarks."
        />
        <ListRow
          to="/suggestions"
          icon={Sparkles}
          tone="green"
          title="Daily suggestions"
          subtitle="Prevention guidance from the Lancet Commission."
        />
      </GroupedList>

      <GroupedList
        header="Memory"
        footer="Save what you mean to do; you'll be asked about it later, and always shown the list."
      >
        <ListRow
          to="/reminders"
          icon={ListChecks}
          tone="blue"
          title="Things to remember"
          subtitle="Reminders that test you, then help you."
        />
      </GroupedList>

      <Disclaimer />
    </Shell>
  );
}
