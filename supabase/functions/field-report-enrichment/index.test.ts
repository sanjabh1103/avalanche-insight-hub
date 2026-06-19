import { assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { handleFieldReportEnrichment } from "./index.ts";

Deno.test({
  name: "handleFieldReportEnrichment returns 400 when payload is invalid",
  sanitizeOps: false,
  sanitizeResources: false,
  async fn() {
    const req = new Request("https://example.com/functions/v1/field-report-enrichment", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({}),
    });

    const res = await handleFieldReportEnrichment(req);
    assertEquals(res.status, 400);

    const body = await res.json();
    assertEquals(body.error, "Invalid field report payload");
  }
});
