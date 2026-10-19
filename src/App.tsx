import { Suspense, lazy, useMemo } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes, Navigate, useSearchParams } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/ThemeProvider";
import AppLayout from "@/components/AppLayout";
import AppErrorBoundary from "@/components/AppErrorBoundary";
import { getDefaultFeatureFlags } from "@/lib/featureFlags";
// FIX-13 (L-4): Wrap /knowledge route in RoleAccessGate for defense-in-depth.
// The page already has a client-side loopback check, but the route should
// also be gated by role before customer-facing promotion.
import RoleAccessGate from "@/components/RoleAccessGate";

const queryClient = new QueryClient();
const LandingPage = lazy(() => import("./pages/LandingPage.tsx"));
const ForecastPage = lazy(() => import("./pages/Index.tsx"));
const MethodsPage = lazy(() => import("./pages/MethodsPage.tsx"));
const AdminPage = lazy(() => import("./pages/AdminPage.tsx"));
const ScientistPage = lazy(() => import("./pages/ScientistPage.tsx"));
const ScientistDailyVerificationPage = lazy(() => import("./pages/ScientistDailyVerificationPage.tsx"));
const ContinuousVerificationPage = lazy(() => import("./pages/ContinuousVerificationPage.tsx"));
const ScientistPartnerIntakePage = lazy(() => import("./pages/ScientistPartnerIntakePage.tsx"));
const ReportPage = lazy(() => import("./pages/ReportPage.tsx"));
const KnowledgeGraphPage = lazy(() => (
  import.meta.env.DEV
    ? import("./pages/KnowledgeGraphPage.tsx")
    : import("./pages/KnowledgeGraphUnavailable.tsx")
));
const NotFoundPage = lazy(() => import("./pages/NotFound.tsx"));

function RouteLoadingShell({ label }: { label: string }) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-6 text-foreground">
      <div className="rounded-3xl border border-border/70 bg-card/70 px-6 py-5 shadow-2xl shadow-black/20 backdrop-blur-2xl">
        <div className="flex items-center gap-3 text-sm uppercase tracking-[0.22em] text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
          <span>{label}</span>
        </div>
      </div>
    </div>
  );
}

function FixtureRedirect() {
  const [params] = useSearchParams();
  if (params.get('fixture')) {
    return <Navigate to={`/explore?${params.toString()}`} replace />;
  }
  return null;
}

const App = () => {
  const flags = useMemo(() => getDefaultFeatureFlags(), []);
  return (
  <ThemeProvider defaultTheme="dark" storageKey="avalanche-insight-theme">
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <Routes>
              <Route element={<AppLayout />}>
                <Route
                  path="/"
                  element={(
                    <Suspense fallback={<RouteLoadingShell label="Loading dashboard" />}>
                      <FixtureRedirect />
                      <LandingPage />
                    </Suspense>
                  )}
                />
                <Route
                  path="/explore"
                  element={(
                    <Suspense fallback={<RouteLoadingShell label="Loading forecast workspace" />}>
                      <ForecastPage />
                    </Suspense>
                  )}
                />
                <Route
                  path="/methods"
                  element={(
                    <Suspense fallback={<RouteLoadingShell label="Loading methods" />}>
                      <MethodsPage />
                    </Suspense>
                  )}
                />
                <Route
                  path="/knowledge"
                  element={(
                    // FIX-13 (L-4): RoleAccessGate provides defense-in-depth
                    // before customer-facing promotion. The page's loopback
                    // check remains as a second layer.
                    <RoleAccessGate allowedRoles={["scientist", "admin"]}>
                      <Suspense fallback={<RouteLoadingShell label="Loading knowledge graph" />}>
                        <KnowledgeGraphPage />
                      </Suspense>
                    </RoleAccessGate>
                  )}
                />
                <Route
                  path="/admin"
                  element={(
                    <Suspense fallback={<RouteLoadingShell label="Loading admin workspace" />}>
                      <AdminPage />
                    </Suspense>
                  )}
                />
                <Route
                  path="/scientist"
                  element={(
                    <Suspense fallback={<RouteLoadingShell label="Loading scientist workspace" />}>
                      <ScientistPage />
                    </Suspense>
                  )}
                />
                <Route
                  path="/scientist/daily-verification"
                  element={(
                    <Suspense fallback={<RouteLoadingShell label="Loading daily verification" />}>
                      <ScientistDailyVerificationPage />
                    </Suspense>
                  )}
                />
                <Route
                  path="/scientist/continuous-verification"
                  element={(
                    <Suspense fallback={<RouteLoadingShell label="Loading continuous verification" />}>
                      <ContinuousVerificationPage />
                    </Suspense>
                  )}
                />
                {flags.partnerIntake ? (
                  <Route
                    path="/scientist/partner-intake"
                    element={(
                      <Suspense fallback={<RouteLoadingShell label="Loading partner intake" />}>
                        <ScientistPartnerIntakePage />
                      </Suspense>
                    )}
                  />
                ) : null}
                <Route
                  path="/report"
                  element={(
                    <Suspense fallback={<RouteLoadingShell label="Loading report form" />}>
                      <ReportPage />
                    </Suspense>
                  )}
                />
                {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
                <Route
                  path="*"
                  element={(
                    <Suspense fallback={<RouteLoadingShell label="Loading route" />}>
                      <NotFoundPage />
                    </Suspense>
                  )}
                />
              </Route>
            </Routes>
          </BrowserRouter>
        </TooltipProvider>
      </QueryClientProvider>
    </AppErrorBoundary>
  </ThemeProvider>
  );
};

export default App;
