# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: e2e.spec.ts >> Full responder flow >> polling fallback — UI shows stale indicator when data is aging
- Location: tests/e2e.spec.ts:122:3

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByRole('heading', { name: 'Situation Report' }).or(getByRole('heading', { name: 'Alerts' }))
Expected: visible
Error: strict mode violation: getByRole('heading', { name: 'Situation Report' }).or(getByRole('heading', { name: 'Alerts' })) resolved to 2 elements:
    1) <h2 class="text-xs font-bold uppercase tracking-wider text-gray-300">Situation Report</h2> aka getByRole('heading', { name: 'Situation Report' })
    2) <h2 class="text-xs font-bold uppercase tracking-wider text-gray-300">Alerts</h2> aka getByRole('heading', { name: 'Alerts' })

Call log:
  - Expect "toBeVisible" with timeout 15000ms
  - waiting for getByRole('heading', { name: 'Situation Report' }).or(getByRole('heading', { name: 'Alerts' }))

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - banner [ref=e4]:
    - generic [ref=e5]:
      - generic [ref=e6]: ResQNet-SAGE
      - navigation "Main navigation" [ref=e7]:
        - link "Dashboard" [ref=e8] [cursor=pointer]:
          - /url: /dashboard
        - link "Hypotheses" [ref=e9] [cursor=pointer]:
          - /url: /hypotheses
        - link "Planning" [ref=e10] [cursor=pointer]:
          - /url: /planning
        - link "Simulation" [ref=e11] [cursor=pointer]:
          - /url: /simulation
        - link "Field" [ref=e12] [cursor=pointer]:
          - /url: /field
        - link "Audit" [ref=e13] [cursor=pointer]:
          - /url: /audit
    - generic [ref=e14]:
      - switch "Enable low-bandwidth mode" [ref=e15] [cursor=pointer]:
        - img [ref=e16]
        - generic [ref=e18]: Low BW
      - status "Network online" [ref=e19]: Online
      - status "All changes synced" [ref=e21]: Synced
      - generic "Current user" [ref=e22]: admin@demo.disasteradmin
      - button "Sign out" [ref=e23] [cursor=pointer]
  - main [ref=e24]:
    - generic [ref=e25]:
      - application "Situation awareness map" [ref=e26]:
        - generic [ref=e27]:
          - generic [ref=e28]:
            - region "Map" [ref=e29]
            - group [ref=e30]:
              - generic "Toggle attribution" [ref=e31] [cursor=pointer]
              - link "MapLibre" [ref=e33] [cursor=pointer]:
                - /url: https://maplibre.org/
          - generic [ref=e34]:
            - generic [ref=e35]:
              - heading "Map Layers" [level=2] [ref=e36]
              - generic [ref=e37]: 7 active
            - generic [ref=e38]:
              - generic [ref=e39]:
                - checkbox "Toggle Alerts" [ref=e40] [cursor=pointer]:
                  - img [ref=e41]
                - generic [ref=e43]:
                  - generic [ref=e44]:
                    - img [ref=e45]
                    - generic [ref=e47]: Alerts
                  - generic [ref=e48]:
                    - 'generic "Data age: no data" [ref=e49]':
                      - generic [ref=e51]: no data
                    - generic [ref=e52]: 0 features
              - generic [ref=e53]:
                - checkbox "Toggle Building Footprints" [ref=e54] [cursor=pointer]:
                  - img [ref=e55]
                - generic [ref=e57]:
                  - generic [ref=e58]:
                    - img [ref=e59]
                    - generic [ref=e61]: Building Footprints
                  - generic [ref=e62]:
                    - 'generic "Data age: 1m ago" [ref=e63]':
                      - generic [ref=e65]: 1m ago
                    - generic [ref=e66]: 10 features
              - generic [ref=e67]:
                - checkbox "Toggle Cell Towers" [ref=e68] [cursor=pointer]:
                  - img [ref=e69]
                - generic [ref=e71]:
                  - generic [ref=e72]:
                    - img [ref=e73]
                    - generic [ref=e75]: Cell Towers
                  - generic [ref=e76]:
                    - 'generic "Data age: 2h ago" [ref=e77]':
                      - generic [ref=e79]: 2h ago
                    - generic [ref=e80]: 5 features
              - generic [ref=e81]:
                - checkbox "Toggle Flood Probability" [checked] [ref=e82] [cursor=pointer]:
                  - img [ref=e83]
                - generic [ref=e86]:
                  - generic [ref=e87]:
                    - img [ref=e88]
                    - generic [ref=e90]: Flood Probability
                  - generic [ref=e91]:
                    - 'generic "Data age: 205h ago" [ref=e92]':
                      - generic [ref=e94]: 205h ago
                    - generic [ref=e95]: 20 features
              - generic [ref=e96]:
                - checkbox "Toggle Hazard Zones" [checked] [ref=e97] [cursor=pointer]:
                  - img [ref=e98]
                - generic [ref=e101]:
                  - generic [ref=e102]:
                    - img [ref=e103]
                    - generic [ref=e105]: Hazard Zones
                  - generic [ref=e106]:
                    - 'generic "Data age: no data" [ref=e107]':
                      - generic [ref=e109]: no data
                    - generic [ref=e110]: 0 features
              - generic [ref=e111]:
                - checkbox "Toggle Hospitals" [checked] [ref=e112] [cursor=pointer]:
                  - img [ref=e113]
                - generic [ref=e116]:
                  - generic [ref=e117]:
                    - img [ref=e118]
                    - generic [ref=e120]: Hospitals
                  - generic [ref=e121]:
                    - 'generic "Data age: 21m ago" [ref=e122]':
                      - generic [ref=e124]: 21m ago
                    - generic [ref=e125]: 2 features
              - generic [ref=e126]:
                - checkbox "Toggle Observations" [checked] [ref=e127] [cursor=pointer]:
                  - img [ref=e128]
                - generic [ref=e131]:
                  - generic [ref=e132]:
                    - img [ref=e133]
                    - generic [ref=e135]: Observations
                  - generic [ref=e136]:
                    - 'generic "Data age: 205h ago" [ref=e137]':
                      - generic [ref=e139]: 205h ago
                    - generic [ref=e140]: 50 features
              - generic [ref=e141]:
                - checkbox "Toggle Responders (Live)" [checked] [ref=e142] [cursor=pointer]:
                  - img [ref=e143]
                - generic [ref=e146]:
                  - generic [ref=e147]:
                    - img [ref=e148]
                    - generic [ref=e150]: Responders (Live)
                  - generic [ref=e151]:
                    - 'generic "Data age: 1m ago" [ref=e152]':
                      - generic [ref=e154]: 1m ago
                    - generic [ref=e155]: 5 features
              - generic [ref=e156]:
                - checkbox "Toggle Road Network" [checked] [ref=e157] [cursor=pointer]:
                  - img [ref=e158]
                - generic [ref=e161]:
                  - generic [ref=e162]:
                    - img [ref=e163]
                    - generic [ref=e165]: Road Network
                  - generic [ref=e166]:
                    - 'generic "Data age: 1m ago" [ref=e167]':
                      - generic [ref=e169]: 1m ago
                    - generic [ref=e170]: 20 features
              - generic [ref=e171]:
                - checkbox "Toggle Sensors" [ref=e172] [cursor=pointer]:
                  - img [ref=e173]
                - generic [ref=e175]:
                  - generic [ref=e176]:
                    - img [ref=e177]
                    - generic [ref=e179]: Sensors
                  - generic [ref=e180]:
                    - 'generic "Data age: 1m ago" [ref=e181]':
                      - generic [ref=e183]: 1m ago
                    - generic [ref=e184]: 2 features
              - generic [ref=e185]:
                - checkbox "Toggle Shelters" [checked] [ref=e186] [cursor=pointer]:
                  - img [ref=e187]
                - generic [ref=e190]:
                  - generic [ref=e191]:
                    - img [ref=e192]
                    - generic [ref=e194]: Shelters
                  - generic [ref=e195]:
                    - 'generic "Data age: 1m ago" [ref=e196]':
                      - generic [ref=e198]: 1m ago
                    - generic [ref=e199]: 3 features
            - button "Start drawing zone" [ref=e201] [cursor=pointer]: Draw Zone
          - generic [ref=e203]:
            - heading "Legend" [level=2] [ref=e204]
            - generic [ref=e205]:
              - heading "Data Freshness" [level=3] [ref=e206]
              - generic [ref=e207]:
                - generic [ref=e210]: < 5 min (fresh)
                - generic [ref=e213]: 5–60 min (aging)
                - generic [ref=e216]: "> 60 min (stale)"
            - generic [ref=e217]:
              - heading "Road Passability" [level=3] [ref=e218]
              - generic [ref=e219]:
                - generic [ref=e222]: Open
                - generic [ref=e225]: Partial
                - generic [ref=e228]: Blocked
                - generic [ref=e231]: Dangerous
            - generic [ref=e232]:
              - heading "Flood Probability" [level=3] [ref=e233]
              - generic [ref=e234]:
                - generic [ref=e237]: High probability
                - generic [ref=e240]: Medium
                - generic [ref=e243]: Low
            - paragraph [ref=e245]: Stale data (>1h) shown in degraded colors. Flood heatmap is semi-transparent for uncertainty.
          - status "50 observation markers on map" [ref=e246]: 50 observations
      - complementary "Situation panels" [ref=e247]:
        - generic [ref=e248]:
          - heading "Rivertown Cyclone-Flood 2026" [level=1] [ref=e249]
          - generic [ref=e250]:
            - generic [ref=e251]: cyclone_flood
            - generic [ref=e252]: "Severity: major"
            - generic [ref=e253]: "Status: active"
        - region "Feed Health" [ref=e255]:
          - generic [ref=e256]:
            - heading "Feed Health" [level=2] [ref=e257]
            - status "Data stale — 49 feeds down" [ref=e258]
          - alert "Data stale or unavailable — all feeds are down" [ref=e259]: Data stale — all feeds are down. Showing last known values.
          - list [ref=e260]:
            - listitem "Feed simulator:rescue-ball-001:device_temperature, status down, data age unavailable" [ref=e261]:
              - generic [ref=e262]:
                - generic [ref=e263]: ✕
                - generic [ref=e264]: simulator:rescue-ball-001:device_temperature
              - generic [ref=e265]:
                - generic [ref=e266]: down
                - generic [ref=e267]: unavailable
            - listitem "Feed citizen:user_005:rescue_request, status down, data age unavailable" [ref=e268]:
              - generic [ref=e269]:
                - generic [ref=e270]: ✕
                - generic [ref=e271]: citizen:user_005:rescue_request
              - generic [ref=e272]:
                - generic [ref=e273]: down
                - generic [ref=e274]: unavailable
            - listitem "Feed stac:S1A_IW_GRDH_1SDV_20260720T054000_20260720T054030_055001:sentinel-1, status down, data age unavailable" [ref=e275]:
              - generic [ref=e276]:
                - generic [ref=e277]: ✕
                - generic [ref=e278]: stac:S1A_IW_GRDH_1SDV_20260720T054000_20260720T054030_055001:sentinel-1
              - generic [ref=e279]:
                - generic [ref=e280]: down
                - generic [ref=e281]: unavailable
            - listitem "Feed cap:flood_update:flood_warning, status down, data age unavailable" [ref=e282]:
              - generic [ref=e283]:
                - generic [ref=e284]: ✕
                - generic [ref=e285]: cap:flood_update:flood_warning
              - generic [ref=e286]:
                - generic [ref=e287]: down
                - generic [ref=e288]: unavailable
            - listitem "Feed simulator:rescue-ball-002:device_temperature, status down, data age unavailable" [ref=e289]:
              - generic [ref=e290]:
                - generic [ref=e291]: ✕
                - generic [ref=e292]: simulator:rescue-ball-002:device_temperature
              - generic [ref=e293]:
                - generic [ref=e294]: down
                - generic [ref=e295]: unavailable
            - listitem "Feed simulator:rescue-ball-001:altitude, status down, data age unavailable" [ref=e296]:
              - generic [ref=e297]:
                - generic [ref=e298]: ✕
                - generic [ref=e299]: simulator:rescue-ball-001:altitude
              - generic [ref=e300]:
                - generic [ref=e301]: down
                - generic [ref=e302]: unavailable
            - listitem "Feed official:agency_07:evacuation_progress, status down, data age unavailable" [ref=e303]:
              - generic [ref=e304]:
                - generic [ref=e305]: ✕
                - generic [ref=e306]: official:agency_07:evacuation_progress
              - generic [ref=e307]:
                - generic [ref=e308]: down
                - generic [ref=e309]: unavailable
            - listitem "Feed official:agency_08:shelter_occupancy, status down, data age unavailable" [ref=e310]:
              - generic [ref=e311]:
                - generic [ref=e312]: ✕
                - generic [ref=e313]: official:agency_08:shelter_occupancy
              - generic [ref=e314]:
                - generic [ref=e315]: down
                - generic [ref=e316]: unavailable
            - listitem "Feed sensorthings:RIVG-01:water_level, status down, data age unavailable" [ref=e317]:
              - generic [ref=e318]:
                - generic [ref=e319]: ✕
                - generic [ref=e320]: sensorthings:RIVG-01:water_level
              - generic [ref=e321]:
                - generic [ref=e322]: down
                - generic [ref=e323]: unavailable
            - listitem "Feed official:agency_04:substation_status, status down, data age unavailable" [ref=e324]:
              - generic [ref=e325]:
                - generic [ref=e326]: ✕
                - generic [ref=e327]: official:agency_04:substation_status
              - generic [ref=e328]:
                - generic [ref=e329]: down
                - generic [ref=e330]: unavailable
            - listitem "Feed citizen:user_002:water_level, status down, data age unavailable" [ref=e331]:
              - generic [ref=e332]:
                - generic [ref=e333]: ✕
                - generic [ref=e334]: citizen:user_002:water_level
              - generic [ref=e335]:
                - generic [ref=e336]: down
                - generic [ref=e337]: unavailable
            - listitem "Feed simulator:rescue-ball-002:battery_level, status down, data age unavailable" [ref=e338]:
              - generic [ref=e339]:
                - generic [ref=e340]: ✕
                - generic [ref=e341]: simulator:rescue-ball-002:battery_level
              - generic [ref=e342]:
                - generic [ref=e343]: down
                - generic [ref=e344]: unavailable
            - paragraph [ref=e345]: +37 more feeds
        - region "Situation Report" [ref=e347]:
          - heading "Situation Report" [level=2] [ref=e349]
          - generic [ref=e350]:
            - generic [ref=e351]:
              - generic [ref=e352]: "0"
              - generic [ref=e353]: Observations
            - generic [ref=e354]:
              - generic [ref=e355]: "0"
              - generic [ref=e356]: Hazards
            - generic [ref=e357]:
              - generic [ref=e358]: "5"
              - generic [ref=e359]: Hypotheses
            - generic [ref=e360]:
              - generic [ref=e361]: "1"
              - generic [ref=e362]: Alerts
        - region "Alerts" [ref=e364]:
          - heading "Alerts" [level=2] [ref=e366]
          - generic [ref=e368]:
            - generic [ref=e369]:
              - generic [ref=e370]: Trapped person reported in Ward-2-Riverside
              - generic [ref=e371]: critical
            - paragraph [ref=e372]: "Citizen report: family of 4 trapped on rooftop near Bridge BR-04. Water level rising. Rescue ball deployed."
            - paragraph [ref=e373]: → Dispatch boat rescue team immediately
            - generic [ref=e375]: draft
        - region "Tasks" [ref=e377]:
          - heading "Tasks" [level=2] [ref=e379]
          - generic [ref=e381]:
            - generic [ref=e382]: Rescue trapped person
            - generic [ref=e383]:
              - generic [ref=e384]: high
              - generic [ref=e385]: in_progress
```

# Test source

```ts
  30  |     await expect(mapContainer.or(lowBwPlaceholder)).toBeVisible({ timeout: 15_000 })
  31  | 
  32  |     // The incident title should appear in the sidebar.
  33  |     await expect(page.locator('aside')).toContainText(/Rivertown|Flood|Incident/i, { timeout: 15_000 })
  34  | 
  35  |     // Observation markers should be visible on the map when data is present.
  36  |     await expect(page.locator('[data-testid="observation-marker"]')).toBeVisible({ timeout: 15_000 })
  37  |   })
  38  | 
  39  |   test('simulator starts and device count is visible', async ({ page }) => {
  40  |     await page.getByRole('link', { name: 'Simulation' }).click()
  41  |     await page.waitForURL('**/simulation', { timeout: 10_000 })
  42  | 
  43  |     // The simulator status panel should show a state (stopped/running/paused).
  44  |     await expect(page.locator('body')).toContainText(/stopped|running|paused/i, { timeout: 15_000 })
  45  | 
  46  |     // Start the simulator if it's stopped.
  47  |     const startButton = page.getByRole('button', { name: /start/i })
  48  |     if (await startButton.isVisible({ timeout: 3_000 }).catch(() => false)) {
  49  |       await startButton.click()
  50  |       // Wait for state to transition to running.
  51  |       await expect(page.locator('body')).toContainText(/running/i, { timeout: 15_000 })
  52  |     }
  53  |   })
  54  | 
  55  |   test('alert appears in the dashboard sidebar', async ({ page }) => {
  56  |     // Navigate to dashboard and wait for alerts panel.
  57  |     await page.waitForURL('**/dashboard')
  58  |     // The alerts panel should be present (may be empty or have alerts).
  59  |     await expect(page.getByRole('heading', { name: 'Alerts' })).toBeVisible({ timeout: 15_000 })
  60  |     // Synced badge should be visible when online with no pending outbox items.
  61  |     await expect(page.locator('[data-testid="synced-badge"]')).toBeVisible({ timeout: 15_000 })
  62  |   })
  63  | 
  64  |   test('operator can approve an alert from the planning page', async ({ page }) => {
  65  |     await page.getByRole('link', { name: 'Planning' }).click()
  66  |     await page.waitForURL('**/planning', { timeout: 10_000 })
  67  |     // Alert cards with approve buttons should be visible on the planning page.
  68  |     await expect(page.locator('[data-testid="alert-card"]')).toBeVisible({ timeout: 15_000 })
  69  |     await expect(page.locator('[data-testid="approve-button"]')).toBeVisible({ timeout: 15_000 })
  70  |   })
  71  | 
  72  |   test('field responder view shows assigned tasks', async ({ page }) => {
  73  |     await page.getByRole('link', { name: 'Field' }).click()
  74  |     await page.waitForURL('**/field', { timeout: 10_000 })
  75  | 
  76  |     // The field page should show the "My Tasks" section.
  77  |     await expect(page.getByRole('heading', { name: 'My Tasks' })).toBeVisible({ timeout: 15_000 })
  78  |     // Task cards should be visible when tasks are assigned.
  79  |     await expect(page.locator('[data-testid="task-card"]')).toBeVisible({ timeout: 15_000 })
  80  |   })
  81  | 
  82  |   test('outbox pending badge appears when offline, synced badge on reconnect', async ({ page }) => {
  83  |     await page.getByRole('link', { name: 'Field' }).click()
  84  |     await page.waitForURL('**/field', { timeout: 10_000 })
  85  | 
  86  |     // Go offline and update a task status to queue it in the outbox.
  87  |     await page.context().setOffline(true)
  88  |     const taskSelect = page.locator('select[aria-label^="Update status for task"]').first()
  89  |     if (await taskSelect.isVisible({ timeout: 5_000 }).catch(() => false)) {
  90  |       await taskSelect.selectOption('in_progress')
  91  | 
  92  |       // Pending badge should appear when mutation is queued in outbox.
  93  |       await expect(page.locator('[data-testid="pending-badge"]')).toBeVisible({ timeout: 15_000 })
  94  |     }
  95  | 
  96  |     // Go back online — synced badge should reappear after sync.
  97  |     await page.context().setOffline(false)
  98  |     await expect(page.locator('[data-testid="synced-badge"]')).toBeVisible({ timeout: 30_000 })
  99  |   })
  100 | 
  101 |   test('task status update from field view reaches command centre', async ({ page }) => {
  102 |     // Navigate to field view.
  103 |     await page.getByRole('link', { name: 'Field' }).click()
  104 |     await page.waitForURL('**/field', { timeout: 10_000 })
  105 | 
  106 |     // If there are tasks, update the first one's status.
  107 |     const taskSelect = page.locator('select[aria-label^="Update status for task"]').first()
  108 |     if (await taskSelect.isVisible({ timeout: 5_000 }).catch(() => false)) {
  109 |       await taskSelect.selectOption('in_progress')
  110 | 
  111 |       // Wait for the toast confirmation.
  112 |       await expect(page.locator('[role="alert"]')).toContainText(/in_progress/i, { timeout: 10_000 })
  113 | 
  114 |       // Navigate back to dashboard and verify the task status propagated.
  115 |       await page.getByRole('link', { name: 'Dashboard' }).click()
  116 |       await page.waitForURL('**/dashboard', { timeout: 10_000 })
  117 |       // The tasks panel should show the updated status.
  118 |       await expect(page.getByRole('heading', { name: 'Tasks' })).toBeVisible({ timeout: 15_000 })
  119 |     }
  120 |   })
  121 | 
  122 |   test('polling fallback — UI shows stale indicator when data is aging', async ({ page }) => {
  123 |     // The dashboard uses TanStack Query with refetchInterval. When data is
  124 |     // stale, the StaleState component renders. This test verifies the UI
  125 |     // handles slow/aging data gracefully (doesn't crash, shows panels).
  126 |     await page.waitForURL('**/dashboard')
  127 |     // Wait for the situation report panel to render.
  128 |     await expect(page.getByRole('heading', { name: 'Situation Report' }).or(
  129 |       page.getByRole('heading', { name: 'Alerts' })
> 130 |     )).toBeVisible({ timeout: 15_000 })
      |        ^ Error: expect(locator).toBeVisible() failed
  131 |   })
  132 | })
  133 | 
```