import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import "@/styles/global.css";
import "@/i18n";
import { Providers } from "@/app/providers";
import { router } from "@/app/routes";

const root = document.getElementById("root");
if (!root) throw new Error("#root missing");

// No <StrictMode>: its dev-only double-mount races @react-three/fiber 9.x's delayed
// (500 ms) root teardown — the remounted Canvas root is deleted from the frame loop and
// its GL context force-lost, freezing every scene. Re-wrap once R3F handles remounts.
createRoot(root).render(
  <Providers>
    <RouterProvider router={router} />
  </Providers>,
);
