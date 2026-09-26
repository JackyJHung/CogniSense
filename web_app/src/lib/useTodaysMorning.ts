import { useEffect, useState } from "react";
import { api, ApiError, type MorningCheckin } from "./api";

export interface TodaysMorning {
  /** Today's morning check-in, in the user's own day; null when there is none. */
  morning: MorningCheckin | null;
  loading: boolean;
  error: string | null;
}

/* Today's morning check-in, asked of the server each time. It used to be
 * remembered in localStorage from whenever the morning page last ran, which
 * went wrong both ways: on a new device the evening page said there was no
 * morning check-in, and on a device last used yesterday it tested tonight
 * against yesterday's cues. The desktop app asks the server for the same
 * reason. */
export function useTodaysMorning(userId: number | undefined): TodaysMorning {
  const [state, setState] = useState<TodaysMorning>({ morning: null, loading: true, error: null });

  useEffect(() => {
    if (userId === undefined) return;
    let ignore = false;
    api.get<MorningCheckin>(`/checkins/morning/today/${userId}`).then(
      (morning) => {
        if (!ignore) setState({ morning, loading: false, error: null });
      },
      (err) => {
        if (ignore) return;
        // 404 is the ordinary answer before the morning check-in.
        const none = err instanceof ApiError && err.status === 404;
        setState({
          morning: null,
          loading: false,
          error: none ? null : err instanceof Error ? err.message : "Could not load today's check-in",
        });
      },
    );
    return () => {
      ignore = true;
    };
  }, [userId]);

  return state;
}
