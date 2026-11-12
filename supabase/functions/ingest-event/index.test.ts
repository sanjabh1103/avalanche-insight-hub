import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { handleIngestEvent } from "./index.ts";

Deno.test("handleIngestEvent returns 401 when REQUIRE_JOB_AUTH is enabled and token is missing", async () => {
  // Set env vars
  const oldRequireAuth = Deno.env.get("REQUIRE_JOB_AUTH");
  const oldJobToken = Deno.env.get("JOB_DISPATCH_TOKEN");
  Deno.env.set("REQUIRE_JOB_AUTH", "true");
  Deno.env.set("JOB_DISPATCH_TOKEN", "super-secret-token");

  try {
    const req = new Request("https://example.com/functions/v1/ingest-event", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ lat: 40.0, lng: -105.0 }),
    });

    const res = await handleIngestEvent(req);
    assertEquals(res.status, 401);

    const body = await res.json();
    assertEquals(body.error, "Unauthorized system call");
  } finally {
    // Restore env vars
    if (oldRequireAuth !== undefined) Deno.env.set("REQUIRE_JOB_AUTH", oldRequireAuth);
    else Deno.env.delete("REQUIRE_JOB_AUTH");

    if (oldJobToken !== undefined) Deno.env.set("JOB_DISPATCH_TOKEN", oldJobToken);
    else Deno.env.delete("JOB_DISPATCH_TOKEN");
  }
});

Deno.test("handleIngestEvent accepts request when Authorization header matches JOB_DISPATCH_TOKEN", async () => {
  const oldRequireAuth = Deno.env.get("REQUIRE_JOB_AUTH");
  const oldJobToken = Deno.env.get("JOB_DISPATCH_TOKEN");
  Deno.env.set("REQUIRE_JOB_AUTH", "true");
  Deno.env.set("JOB_DISPATCH_TOKEN", "super-secret-token");

  try {
    const req = new Request("https://example.com/functions/v1/ingest-event", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer super-secret-token",
      },
      // Since it passes auth, it will proceed to check coordinates/payload.
      // We send invalid coordinates so it returns 400 instead of attempting DB operations.
      body: JSON.stringify({ lat: "invalid", lng: -105.0 }),
    });

    const res = await handleIngestEvent(req);
    // It passed the 401 auth gate and failed on payload validation (400)
    assertEquals(res.status, 400);

    const body = await res.json();
    assertEquals(body.error, "Invalid coordinates");
  } finally {
    if (oldRequireAuth !== undefined) Deno.env.set("REQUIRE_JOB_AUTH", oldRequireAuth);
    else Deno.env.delete("REQUIRE_JOB_AUTH");

    if (oldJobToken !== undefined) Deno.env.set("JOB_DISPATCH_TOKEN", oldJobToken);
    else Deno.env.delete("JOB_DISPATCH_TOKEN");
  }
});
