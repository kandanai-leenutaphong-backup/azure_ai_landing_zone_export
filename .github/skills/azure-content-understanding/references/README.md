# Original Documentation

Prefer these first-party contracts over remembered SDK signatures or generic model
quickstarts. Downloaded source pages are internal reference material and are not
bundled in this skill. [Source observations](sources.json).

| Source | Use |
| --- | --- |
| [Native Python SDK](https://learn.microsoft.com/en-us/python/api/overview/azure/ai-contentunderstanding-readme?view=azure-python) | Installation, async client, native analyzer/result models and supported API versions |
| [SDK source](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/contentunderstanding/azure-ai-contentunderstanding) | Microsoft package implementation and samples, not an alternate runtime copy |
| [Prebuilt analyzers](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/concepts/prebuilt-analyzers) | `prebuilt-layout` versus parsers/search/generative capabilities and model requirements |
| [Analyze binary REST API](https://learn.microsoft.com/en-us/rest/api/contentunderstanding/content-analyzers/analyze-binary?view=rest-contentunderstanding-2025-11-01) | Native binary request and GA operation contract |
| [Language/region support](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/language-region-support) | Regional availability and supported content/languages |
| [Azure Identity](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme?view=azure-python) | Azure CLI/managed identity, token refresh and lifecycle |
| [Function identity connections](https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference#configure-an-identity-based-connection) | Workload identity for a separately authorized host |

The SDK documentation observed on 2026-09-16 lists SDK 1.1.0 with API 2025-11-01.
The executable recipe additionally verifies its returned analyzer/API fields.
Documentation and installed code are evidence, not authorization to process data.