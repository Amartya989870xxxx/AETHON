import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell, MobileNav } from "./components/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ToastProvider } from "./components/toast";
import { TimeWindowProvider } from "./components/TimeWindow";
import { AlertsLiveProvider, useAlertsLive } from "./components/AlertsLive";
import { CityMapScreen } from "./screens/CityMap";
import { TrajectoryScreen } from "./screens/Trajectory";
import { AlertsScreen } from "./screens/Alerts";
import { AnalyticsScreen } from "./screens/Analytics";
import { WatchlistScreen } from "./screens/Watchlist";
import { AuditScreen } from "./screens/Audit";

export function App() {
  return (
    <ToastProvider>
      <TimeWindowProvider>
        <AlertsLiveProvider>
          <Shell />
        </AlertsLiveProvider>
      </TimeWindowProvider>
    </ToastProvider>
  );
}

function Shell() {
  const location = useLocation();
  const { status, unseenCount } = useAlertsLive();

  return (
    <AppShell socketStatus={status} liveAlertCount={unseenCount}>
      <ErrorBoundary key={location.pathname}>
        <div key={location.pathname} className="animate-fade-up">
          <Routes location={location}>
            <Route path="/" element={<Navigate to="/map" replace />} />
            <Route path="/map" element={<CityMapScreen />} />
            <Route path="/trajectory" element={<TrajectoryScreen />} />
            <Route path="/alerts" element={<AlertsScreen />} />
            <Route path="/analytics" element={<AnalyticsScreen />} />
            <Route path="/watchlist" element={<WatchlistScreen />} />
            <Route path="/audit" element={<AuditScreen />} />
            <Route path="*" element={<Navigate to="/map" replace />} />
          </Routes>
        </div>
      </ErrorBoundary>
      <MobileNav liveAlertCount={unseenCount} />
    </AppShell>
  );
}
