import { Shell } from "@/components/layout/Shell";
import { Skeleton } from "@/components/ui";
import { Suspense, lazy } from "react";
import { Outlet, createBrowserRouter } from "react-router-dom";

// Pages lazy-load so the three.js chunk stays out of the initial bundle (§8.7).
const Home = lazy(() => import("@/pages/Home"));
const Chat = lazy(() => import("@/pages/Chat"));
const Evals = lazy(() => import("@/pages/Evals"));
const TokenizerLab = lazy(() => import("@/pages/TokenizerLab"));
const Edge = lazy(() => import("@/pages/Edge"));
const Registry = lazy(() => import("@/pages/Registry"));

function PageFallback() {
  return (
    <div className="mx-auto max-w-6xl p-6">
      <Skeleton className="h-10 w-1/3 mb-6" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

function Layout() {
  return (
    <Shell>
      <Suspense fallback={<PageFallback />}>
        <Outlet />
      </Suspense>
    </Shell>
  );
}

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Home /> },
      { path: "/chat", element: <Chat /> },
      { path: "/evals", element: <Evals /> },
      { path: "/tokenizer", element: <TokenizerLab /> },
      { path: "/edge", element: <Edge /> },
      { path: "/registry", element: <Registry /> },
    ],
  },
]);
