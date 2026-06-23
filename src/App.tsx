import { Suspense, lazy } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/ThemeProvider";
import AppLayout from "@/components/AppLayout";

const queryClient = new QueryClient();
const LandingPage = lazy(() => import("./pages/LandingPage.tsx"));
const ForecastPage = lazy(() => import("./pages/Index.tsx"));
const MethodsPage = lazy(() => import("./pages/MethodsPage.tsx"));
const AdminPage = lazy(() => import("./pages/AdminPage.tsx"));
const ScientistPage = lazy(() => import("./pages/ScientistPage.tsx"));
const ScientistDailyVerificationPage = lazy(() => import("./pages/ScientistDailyVerificationPage.tsx"));
const ScientistPartnerIntakePage = lazy(() => import("./pages/ScientistPartnerIntakePage.tsx"));
const NotFoundPage = lazy(() => import("./pages/NotFound.tsx"));

const partnerIntakeEnabled = import.meta.env.VITE_FEATURE_PARTNER_INTAKE === "true";

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

const App = () => (
  <ThemeProvider defaultTheme="dark" storageKey="avalanche-insight-theme">
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <Routes>
            <Route element={<AppLayout />}>
              <Route
                path="/"
                element={(
                  <Suspense fallback={<RouteLoadingShell label="Loading dashboard" />}>
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
              {partnerIntakeEnabled ? (
                <Route
                  path="/scientist/partner-intake"
                  element={(
                    <Suspense fallback={<RouteLoadingShell label="Loading partner intake" />}>
                      <ScientistPartnerIntakePage />
                    </Suspense>
                  )}
                />
              ) : null}
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
  </ThemeProvider>
);

export default App;
