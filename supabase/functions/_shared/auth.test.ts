import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { authorizeJobRequest } from "./auth.ts";

function withEnv(name: string, value: string, fn: () => Promise<void>): Promise<void> {
  const previous = Deno.env.get(name);
  Deno.env.set(name, value);
  return fn().finally(() => {
    if (previous === undefined) Deno.env.delete(name);
    else Deno.env.set(name, previous);
  });
}

Deno.test("authorizeJobRequest prefers the explicit x-job-token channel", async () => {
  await withEnv("REQUIRE_JOB_AUTH", "true", async () => {
    await withEnv("JOB_DISPATCH_TOKEN", "cron-token", async () => {
      const req = new Request("https://example.test", {
        headers: {
          Authorization: "Bearer user-jwt",
          "x-job-token": "cron-token",
        },
      });
      const supabase = {
        auth: {
          getUser: () => Promise.resolve({ data: { user: null }, error: new Error("must not be called") }),
        },
      };

      const result = await authorizeJobRequest("daily_enrichment", req, supabase);
      assertEquals(result.authorized, true);
      assertEquals(result.audit?.source, "system_token");
    });
  });
});

Deno.test("authorizeJobRequest retains bearer system-token compatibility", async () => {
  await withEnv("REQUIRE_JOB_AUTH", "true", async () => {
    await withEnv("JOB_DISPATCH_TOKEN", "cron-token", async () => {
      const req = new Request("https://example.test", {
        headers: { Authorization: "Bearer cron-token" },
      });
      const result = await authorizeJobRequest("daily_enrichment", req, {
        auth: { getUser: () => Promise.resolve({ data: { user: null }, error: new Error("must not be called") }) },
      });
      assertEquals(result.authorized, true);
    });
  });
});
