# Design Sources Registry

Status legend: ⬜ not yet in repo · ✅ committed to `docs/designs/`

## Claude Design projects

Cloud sessions cannot run `/design-login`; files arrive by founder upload or "Send to Claude Code Web".

| # | File in repo | Project link | Status |
|---|------------------|--------------|--------|
| 1 | `Convergeo_Wireframes.html` ("Convergeo — Wireframes", 2.3MB) | https://claude.ai/design/p/b8eac18e-a463-4659-8316-0c55deb45ddc?file=Convergeo+Wireframes.html | ✅ 2026-07-06 |
| 2 | `Vergeo_Offline_Bundle.html` ("Vergeo — Zambia's National Marketplace", 7.1MB) | https://claude.ai/design/p/9ae07f0f-7f21-4939-9446-415db8e7a993?file=Vergeo.html (presumed) | ✅ 2026-07-06 |
| 3 | `Vergeo_Mobile.html` | https://claude.ai/design/p/9ae07f0f-7f21-4939-9446-415db8e7a993?file=Vergeo+Mobile.html | ⬜ |
| 4 | `Vergeo_Standalone.html` | https://claude.ai/design/p/9ae07f0f-7f21-4939-9446-415db8e7a993?file=Vergeo+Standalone.html | ⬜ |
| 5 | `Vergeo_v1_Standalone.html` ("Vergeo — Zambia's National Marketplace", 7.0MB) | https://claude.ai/design/p/9ae07f0f-7f21-4939-9446-415db8e7a993?file=Vergeo+v1.html | ✅ 2026-07-06 |
| 6 | `Convergeo.html` | https://claude.ai/design/p/5c86be3d-0c2a-42fa-8559-d15ada8c94f5?file=Convergeo.html | ⬜ |
| 7 | `Vergeo_Prototype_offline.html` ("Vergeo — Multi-Vendor Platform · Zambia", 1.4MB) | one of the two "Vergeo Prototype" projects (7e374452… / 019dc6e5…) | ✅ 2026-07-06 |
| 8 | `Vergeo_Prototype_Standalone.html` ("Vergeo — Platform Prototype", 1.5MB) | https://claude.ai/design/p/019dc6e5-8c31-771b-a417-3226a31baa37?file=Vergeo+Prototype.html (presumed) | ✅ 2026-07-06 |
| 9 | `Convergeo_Events_Desktop.html` | https://claude.ai/design/p/019dcaa2-6bd4-71d2-af53-e3d062bed2ce?file=Convergeo+Events+Desktop.html | ⬜ |
| 10 | `Convergeo_Customer_Desktop.html` | https://claude.ai/design/p/019dce70-f5c9-755b-ab24-6dcfac816a79?file=Convergeo+Customer+Desktop.html | ⬜ |
| 11 | `Convergeo_Platform_Standalone.html` ("Convergeo — Platform Prototype", 1.4MB) | https://claude.ai/design/p/019dce70-f5c9-755b-ab24-6dcfac816a79?file=Convergeo+Platform.html | ✅ 2026-07-06 |
| 12 | `Convergeo_Catalogue.html` | https://claude.ai/design/p/019dcaed-c3ef-7c19-9e4d-ee645a98a075?file=Convergeo+Catalogue.html | ⬜ |

**Still missing (6):** Vergeo Mobile · Vergeo Standalone · Convergeo.html · Convergeo Events Desktop · Convergeo Customer Desktop · Convergeo Catalogue. Events Desktop and Catalogue matter most (events is a v1 vertical; catalogue = product-grid reference).

## Live prototype

| Source | Location | Status |
|--------|----------|--------|
| https://vergeo-21ffc.web.app/ (Firebase) | `docs/designs/live-prototype/` | ⛔ egress-blocked from this environment; audit harness ready in `live-prototype/README.md` — allowlist the domain in the environment's network settings or run the harness locally and commit output |

## Selection policy (from founder)

Across variants: pick the strongest elements (state why), including animations/transitions; flag elements worth making **admin-swappable** (hero, banners, featured collections rotate via admin portal). Selection executes at the start of Phase 1 from the committed HTML above.
